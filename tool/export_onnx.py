"""Export the pinned BGE-M3 base as ONE multi-output FP32 ONNX graph (PLAN section 7 steps 1-3, 5) and verify it.

Outputs per batch (tensors stay native; never the [B,T,250002] vocabulary logits):
  dense        [B,1024]    L2-normalized CLS
  sparse       [B,T]       relu(sparse_linear(h)); caller drops specials and keeps max per token ID
  colbert      [B,T-1,1024] normalized(colbert_linear(h[:,1:]) * mask); caller trims each row to its length-1

  .venv\\Scripts\\python.exe -I tool/export_onnx.py [--out generated-artifacts/onnx-fp32] [--verify-only]
Output directory is gitignored. The head is NOT part of this graph (separate identity, PLAN section 7 step 4).
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from transformers import AutoModel, AutoTokenizer

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / '.artifact-staging' / 'import-application-v1' / 'extracted'
BASE = EXT / 'bge-m3-pinned'
VERIFY_TEXTS = [
    'faith',
    'What does the Bible teach about forgiveness?',
    '¿Qué dice la Biblia sobre el amor al prójimo?',
    'Ano ang sinasabi ng kasulatan tungkol sa pagpapakumbaba? 🙏',
    'In the beginning God created the heavens and the earth',
    'Then God said, “Let there be light,” and there was light. ' * 6,  # long, forces padding in a batch
    'שלום עולם',
    'Ἐν ἀρχῇ ἦν ὁ λόγος',
]


class M3(torch.nn.Module):
    def __init__(self, base, sparse, colbert):
        super().__init__()
        self.base, self.sparse, self.colbert = base, sparse, colbert

    def forward(self, input_ids, attention_mask):
        h = self.base(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
        dense = F.normalize(h[:, 0], dim=-1)
        sparse = torch.relu(self.sparse(h)).squeeze(-1)
        col = self.colbert(h[:, 1:]) * attention_mask[:, 1:].unsqueeze(-1).to(h.dtype)
        return dense, sparse, F.normalize(col, dim=-1)


def load_module():
    base = AutoModel.from_pretrained(BASE, dtype=torch.float32, attn_implementation='eager').eval()
    sp = torch.nn.Linear(1024, 1)
    sp.load_state_dict(torch.load(BASE / 'sparse_linear.pt', map_location='cpu', weights_only=True))
    cb = torch.nn.Linear(1024, 1024)
    cb.load_state_dict(torch.load(BASE / 'colbert_linear.pt', map_location='cpu', weights_only=True))
    return M3(base, sp.eval(), cb.eval()).eval()


def export(model, out):
    tok = AutoTokenizer.from_pretrained(BASE)
    ex = tok(['hello world', 'a somewhat longer example sentence for tracing'], padding=True, return_tensors='pt')
    args = (ex['input_ids'], ex['attention_mask'])
    out.mkdir(parents=True, exist_ok=True)
    path = out / 'bge_m3_multi_fp32.onnx'
    t0 = time.perf_counter()
    prog = torch.onnx.export(
        model, args, dynamo=True,
        input_names=['input_ids', 'attention_mask'], output_names=['dense', 'sparse', 'colbert'],
        dynamic_shapes={'input_ids': {0: 'batch', 1: 'seq'}, 'attention_mask': {0: 'batch', 1: 'seq'}})
    prog.save(str(path), external_data=True)
    print(f'exported in {time.perf_counter() - t0:.0f}s -> {path}', flush=True)
    return path


def verify(model, path):
    import onnxruntime as ort
    tok = AutoTokenizer.from_pretrained(BASE)
    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    sess = ort.InferenceSession(str(path), so, providers=['CPUExecutionProvider'])
    unused = {tok.cls_token_id, tok.eos_token_id, tok.pad_token_id, tok.unk_token_id}
    report, ok = [], True
    for batch_texts in (VERIFY_TEXTS, VERIFY_TEXTS[:1], VERIFY_TEXTS[4:6]):  # mixed padding, single, pair
        enc = tok(batch_texts, padding=True, return_tensors='pt')
        with torch.inference_mode():
            td, ts, tc = model(enc['input_ids'], enc['attention_mask'])
        od, os_, oc = sess.run(None, {'input_ids': enc['input_ids'].numpy(), 'attention_mask': enc['attention_mask'].numpy()})
        for i, text in enumerate(batch_texts):
            n = int(enc['attention_mask'][i].sum())
            cos = float(od[i] @ td[i].numpy() / (np.linalg.norm(od[i]) * np.linalg.norm(td[i].numpy())))
            ids = enc['input_ids'][i, :n].tolist()
            def agg(w):
                d = {}
                for t, x in zip(ids, w[:n].tolist()):
                    if t not in unused and x > 0 and x > d.get(t, 0.0):
                        d[t] = x
                return d
            a, b = agg(ts[i].numpy()), agg(os_[i])
            col_err = float(np.abs(oc[i, :n - 1] - tc[i, :n - 1].numpy()).max())
            sp_err = max((abs(a[k] - b[k]) for k in a if k in b), default=0.0)
            row = {'batch': len(batch_texts), 'text': text[:40], 'tokens': n, 'dense_cos': cos,
                   'sparse_same_tokens': set(a) == set(b), 'sparse_max_abs': sp_err, 'colbert_max_abs': col_err}
            row['pass'] = cos >= 0.9999 and row['sparse_same_tokens'] and sp_err < 1e-3 and col_err < 1e-3
            ok &= row['pass']
            report.append(row)
            print(('PASS ' if row['pass'] else 'FAIL ') + json.dumps(row, ensure_ascii=False), flush=True)
    return ok, report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default=str(ROOT / 'generated-artifacts' / 'onnx-fp32'))
    ap.add_argument('--verify-only', action='store_true')
    a = ap.parse_args()
    out = Path(a.out)
    model = load_module()
    path = out / 'bge_m3_multi_fp32.onnx' if a.verify_only else export(model, out)
    ok, report = verify(model, path)
    size = sum(f.stat().st_size for f in out.iterdir() if f.is_file())
    (out / 'verify_report.json').write_text(json.dumps({'pass': ok, 'rows': report, 'bytes': size}, indent=2), 'utf-8')
    print('VERIFY', 'PASSED' if ok else 'FAILED', f'| artifact bytes {size:,}')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
