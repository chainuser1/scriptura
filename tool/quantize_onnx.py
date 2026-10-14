"""INT8 post-training quantization of the FP32 BGE-M3 ONNX graph + first-pass quality check (PLAN section 7, 5-7).

Dynamic quantization needs no calibration data (so nothing from validation/test can leak into it). Variants:
  matmul        MatMul weights, per-channel INT8
  matmul_gather MatMul + the 250,002 x 1,024 word-embedding Gather (the plan's "unquantized embedding table" caveat)

Quality gate here is only a screen: dense cosine of INT8 passage encodings against the SHIPPED FP32 index
(dense_embeddings.f16.npy), plus ColBERT token cosine and sparse agreement against FP32 ORT, on a seeded verse sample.
The ranking-level gate is tool/eval_quantized.py.

  .venv\\Scripts\\python.exe -I tool/quantize_onnx.py [--variants matmul matmul_gather] [--sample 300]
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
from onnxruntime.quantization import QuantType, quantize_dynamic
from transformers import AutoTokenizer

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / '.artifact-staging' / 'import-application-v1' / 'extracted'
FP32 = ROOT / 'generated-artifacts' / 'onnx-fp32' / 'bge_m3_multi_fp32.onnx'
OUTDIR = ROOT / 'generated-artifacts' / 'onnx-int8'
VARIANTS = {'matmul': ['MatMul'], 'matmul_gather': ['MatMul', 'Gather']}


def dir_bytes(p):
    return sum(f.stat().st_size for f in p.parent.glob(p.name + '*') if f.is_file())


def session(path, threads=0):
    so = ort.SessionOptions()
    so.intra_op_num_threads = threads
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(str(path), so, providers=['CPUExecutionProvider'])


def encode(sess, tok, texts, unused, batch=16):
    """-> (dense[N,1024], sparse list[dict], colbert list[[n-1,1024]]) via the ONNX graph; seconds."""
    lens = [len(x) for x in tok(texts, truncation=False)['input_ids']]
    order = np.argsort(lens, kind='stable')
    dense, sparse, col = [None] * len(texts), [None] * len(texts), [None] * len(texts)
    t0 = time.perf_counter()
    for s in range(0, len(order), batch):
        idx = order[s:s + batch]
        e = tok([texts[i] for i in idx], padding=True, return_tensors='np', truncation=False)
        d, w, c = sess.run(None, {'input_ids': e['input_ids'].astype(np.int64), 'attention_mask': e['attention_mask'].astype(np.int64)})
        for j, i in enumerate(idx):
            n = int(e['attention_mask'][j].sum())
            dense[i], col[i] = d[j], c[j, :n - 1]
            m = {}
            for t, x in zip(e['input_ids'][j, :n].tolist(), w[j, :n].tolist()):
                if t not in unused and x > 0 and x > m.get(t, 0.0):
                    m[t] = x
            sparse[i] = m
    return np.stack(dense), sparse, col, time.perf_counter() - t0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--variants', nargs='+', default=list(VARIANTS), choices=list(VARIANTS))
    ap.add_argument('--sample', type=int, default=300)
    ap.add_argument('--skip-quantize', action='store_true')
    a = ap.parse_args()
    OUTDIR.mkdir(parents=True, exist_ok=True)

    r = EXT / 'scripture-retrieval-english-v1'
    verse_ids = np.load(r / 'verse_ids.npy', allow_pickle=False)
    stored = np.load(r / 'dense_embeddings.f16.npy', allow_pickle=False).astype(np.float32)
    texts = [json.loads(l)['scripture_text'] for l in (r / 'scripture_text.jsonl').read_text('utf-8').splitlines()]
    rows = np.sort(np.random.default_rng(20261013).choice(len(texts), a.sample, replace=False))
    sample = [texts[i] for i in rows]
    tok = AutoTokenizer.from_pretrained(EXT / 'bge-m3-pinned')
    unused = {tok.cls_token_id, tok.eos_token_id, tok.pad_token_id, tok.unk_token_id}

    print(f'sample: {len(sample)} verses | FP32 reference session', flush=True)
    fp = session(FP32)
    fd, fs, fc, fp_s = encode(fp, tok, sample, unused)
    print(f'  FP32 ORT: {fp_s:.1f}s  ({fp_s / len(sample) * 1000:.0f} ms/passage); '
          f'cos to shipped index min {np.min(np.sum(fd * stored[rows], 1)):.6f}', flush=True)
    del fp

    report = {'fp32_seconds': fp_s, 'sample': len(sample), 'variants': {}}
    for v in a.variants:
        out = OUTDIR / f'bge_m3_multi_int8_{v}.onnx'
        t0 = time.perf_counter()
        if not a.skip_quantize:
            quantize_dynamic(str(FP32), str(out), op_types_to_quantize=VARIANTS[v], per_channel=True,
                             weight_type=QuantType.QInt8, use_external_data_format=True)
        q_s = time.perf_counter() - t0
        size = dir_bytes(out)
        sess = session(out)
        qd, qs, qc, enc_s = encode(sess, tok, sample, unused)
        cos_idx = np.sum(qd * stored[rows], 1)                       # INT8 passage vs shipped FP32 index
        cos_ref = np.sum(qd * fd, 1)                                  # INT8 vs FP32 ORT
        tok_cos = np.concatenate([np.sum(a_ * b_, 1) / (np.linalg.norm(a_, axis=1) * np.linalg.norm(b_, axis=1))
                                  for a_, b_ in zip(qc, fc)])
        same = np.mean([set(a_) == set(b_) for a_, b_ in zip(qs, fs)])
        jac = np.mean([len(set(a_) & set(b_)) / max(1, len(set(a_) | set(b_))) for a_, b_ in zip(qs, fs)])
        wdiff = np.mean([np.mean([abs(a_[k] - b_[k]) / max(b_[k], 1e-6) for k in set(a_) & set(b_)] or [0]) for a_, b_ in zip(qs, fs)])
        rec = {'bytes': size, 'quantize_seconds': q_s, 'ms_per_passage': enc_s / len(sample) * 1000,
               'dense_cos_vs_shipped_index': {'mean': float(cos_idx.mean()), 'min': float(cos_idx.min()), 'p01': float(np.percentile(cos_idx, 1))},
               'dense_cos_vs_fp32_ort': {'mean': float(cos_ref.mean()), 'min': float(cos_ref.min())},
               'colbert_token_cos_vs_fp32': {'mean': float(tok_cos.mean()), 'min': float(tok_cos.min()), 'p01': float(np.percentile(tok_cos, 1))},
               'sparse_same_token_set_rate': float(same), 'sparse_token_jaccard': float(jac), 'sparse_mean_rel_weight_diff': float(wdiff)}
        report['variants'][v] = rec
        print(f'{v}: {size / 1e9:.2f} GB | {rec["ms_per_passage"]:.0f} ms/passage (FP32 {fp_s / len(sample) * 1000:.0f}) | '
              f'dense cos vs index mean {rec["dense_cos_vs_shipped_index"]["mean"]:.4f} min {rec["dense_cos_vs_shipped_index"]["min"]:.4f} | '
              f'colbert tok cos mean {rec["colbert_token_cos_vs_fp32"]["mean"]:.4f} p01 {rec["colbert_token_cos_vs_fp32"]["p01"]:.4f} | '
              f'sparse jaccard {rec["sparse_token_jaccard"]:.3f}', flush=True)
        del sess
    (OUTDIR / 'screen_report.json').write_text(json.dumps(report, indent=2), 'utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
