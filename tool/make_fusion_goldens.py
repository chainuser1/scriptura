"""Fusion reference for the Rust parity gate (docs/ENGINE_PLAN.md E1): the deployment-shaped pipeline exactly as the
native engine runs it -- INT8 query encoder (batch 1), FP16 genome head, stored weighted-genome rows, stored dense and
sparse indexes, FP16 ColBERT pack -- evaluated for every named search profile on a fixed query list.

  .venv\\Scripts\\python.exe -I tool/make_fusion_goldens.py
Writes test/golden/fusion_engine_int8_matmul.json (verse IDs and scores only; no scripture text).
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy import sparse as sp
from scipy.special import erf
from transformers import AutoTokenizer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_quantized import Pack, variant_path  # noqa: E402
from quantize_onnx import encode, session  # noqa: E402
from reference_search import DEFAULT_EXTRACTED, FAMILY_WEIGHTS, GOLDEN_QUERIES, VOCAB, normalize_rows, top_rows, zscore  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
QUERIES = GOLDEN_QUERIES + ['Who is Captain Moroni?', 'What is faith?', 'Faith vs knowledge', 'ask and ye shall receive',
                            'How do I overcome fear?', '¿Quién fue el capitán Moroni?']
LANE_K, TOP_K = 200, 20


def main():
    r = DEFAULT_EXTRACTED / 'scripture-retrieval-english-v1'
    vids = np.load(r / 'verse_ids.npy')
    dense_idx = np.load(r / 'dense_embeddings.f16.npy').astype(np.float32)
    wg = normalize_rows(np.load(r / 'weighted_genome_embeddings.f16.npy').astype(np.float32))
    with np.load(r / 'sparse_index.csr.npz') as z:
        csr = sp.csr_matrix((z['data'], z['indices'], z['indptr']), shape=tuple(int(x) for x in z['shape']))
    genes = [g for g in (r / 'gene_ids.txt').read_text('utf-8').split('\n') if g]
    sw = np.sqrt(np.array([FAMILY_WEIGHTS.get(g[0], 1.0) for g in genes], dtype=np.float32))
    with np.load(DEFAULT_EXTRACTED / 'scripture-genome-question-hidden4096-optimized' / 'head_fp16.npz') as z:
        w0, b0, w1, b1 = (z[k].astype(np.float32) for k in ('w0', 'b0', 'w1', 'b1'))
    prof = json.loads((ROOT / 'tool' / 'data' / 'fusion_profiles.json').read_text('utf-8'))['profiles']
    pack = Pack()
    tok = AutoTokenizer.from_pretrained(DEFAULT_EXTRACTED / 'bge-m3-pinned')
    unused = {tok.cls_token_id, tok.eos_token_id, tok.pad_token_id, tok.unk_token_id}
    sess = session(variant_path('int8_matmul'), threads=1)

    out = {'meta': {'encoder': 'int8_matmul', 'head': 'head_fp16', 'lane_k': LANE_K, 'top_k': TOP_K,
                    'profiles': {k: [v['echo'], v['spark'], v['thread'], v['root']] for k, v in prof.items()}},
           'queries': []}
    for q in QUERIES:
        d, s, c, _ = encode(sess, tok, [q], unused, batch=1)
        dq = d[0]
        x = dq @ w0.T + b0
        x = 0.5 * x * (1.0 + erf(x / np.sqrt(2.0)))
        g = 1.0 / (1.0 + np.exp(-(x @ w1.T + b1)))
        gw = normalize_rows((g * sw)[None, :])[0]
        sv = np.zeros(VOCAB, dtype=np.float32)
        for t, wgt in s[0].items():
            sv[t] = wgt
        da, ga, sa = (dense_idx @ dq).astype(np.float64), (wg @ gw).astype(np.float64), (csr @ sv).astype(np.float64)
        cand = np.unique(np.concatenate([top_rows(x_, vids, LANE_K) for x_ in (da, sa, ga)]))
        zc = zscore(pack.maxsim(c[0], cand))
        zd, zs, zg = zscore(da[cand]), zscore(sa[cand]), zscore(ga[cand])
        rec = {'text': q, 'candidates': int(len(cand)), 'profiles': {}}
        for name, p in prof.items():
            final = p['echo'] * zd + p['spark'] * zs + p['thread'] * zc + p['root'] * zg
            top = top_rows(final, vids[cand], TOP_K)
            rec['profiles'][name] = {'ids': [int(vids[cand[i]]) for i in top], 'scores': [round(float(final[i]), 6) for i in top]}
        out['queries'].append(rec)
        print(q, '->', rec['candidates'], 'candidates', rec['profiles']['compass']['ids'][:5], flush=True)
    path = ROOT / 'test' / 'golden' / 'fusion_engine_int8_matmul.json'
    path.write_text(json.dumps(out, indent=1), 'utf-8')
    print(path, path.stat().st_size, 'bytes')
    return 0


if __name__ == '__main__':
    sys.exit(main())
