"""Encoder reference outputs for the Rust parity gate (docs/ENGINE_PLAN.md E1): dense, sparse and ColBERT query
encodings from the INT8 graph through Python ONNX Runtime, batch 1, no padding, for a few short multilingual queries.

  .venv\\Scripts\\python.exe -I tool/make_encoder_goldens.py [--variant matmul]
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from transformers import AutoTokenizer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quantize_onnx import EXT, OUTDIR, encode, session  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
QUERIES = ['faith', 'What is faith?', 'Who is Captain Moroni?', 'ask and ye shall receive',
           '¿Quién fue el capitán Moroni?', 'Sino si Nephi?', 'Ano ang kapatawaran?', 'πίστις']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--variant', default='matmul')
    a = ap.parse_args()
    model = OUTDIR / f'bge_m3_multi_int8_{a.variant}.onnx'
    tok = AutoTokenizer.from_pretrained(EXT / 'bge-m3-pinned')
    unused = {tok.cls_token_id, tok.eos_token_id, tok.pad_token_id, tok.unk_token_id}
    sess = session(model, threads=1)
    out = {'meta': {'model': model.name, 'model_sha256_of_graph_file': hashlib.sha256(model.read_bytes()).hexdigest(),
                    'unused_token_ids': sorted(unused), 'note': 'batch 1, no padding; colbert drops the CLS row, '
                    'sparse = max relu weight per token id excluding special ids; floats rounded to 6 decimals'},
           'cases': []}
    for q in QUERIES:
        d, s, c, _ = encode(sess, tok, [q], unused, batch=1)
        ids = tok(q, truncation=False)['input_ids']
        out['cases'].append({'text': q, 'ids': ids, 'dense': [round(float(x), 6) for x in d[0]],
                             'sparse': {str(k): round(float(v), 6) for k, v in sorted(s[0].items())},
                             'colbert_rows': int(c[0].shape[0]),
                             'colbert': [round(float(x), 6) for x in c[0].reshape(-1)]})
    path = ROOT / 'test' / 'golden' / f'encoder_{a.variant}.json'
    path.write_text(json.dumps(out, ensure_ascii=False), 'utf-8')
    print(path, path.stat().st_size, 'bytes')
    return 0


if __name__ == '__main__':
    sys.exit(main())
