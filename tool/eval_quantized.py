"""Ranking-level quality gate for quantized query encoders (PLAN 7 step 7, 12.1) on the 250 q_id x 8 language sample.

Deployment-shaped: the QUERY encoder is the variant under test (ONNX Runtime, as on-device); passages come from the
shipped FP32 dense/sparse/genome index and the offline FP16 ColBERT pack. The unchanged FP16 head consumes the
variant's dense output. `fp32` is the baseline; every other variant is compared with it, paired by q_id.

  .venv\\Scripts\\python.exe -I tool/eval_quantized.py --variants fp32 int8_matmul [int8_matmul_gather]
Gate (PLAN 12.1): relative degradation <= 2% in mean Recall@10 and weighted NDCG@20 for experiment_d,
and no language worse than 5%.
"""
import argparse
import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
from scipy import sparse as sp
from transformers import AutoTokenizer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quantize_onnx import FP32, OUTDIR, encode, session  # noqa: E402
from reference_search import DEFAULT_EXTRACTED, SIGNAL_WEIGHTS, VOCAB, Searcher, normalize_rows, top_rows, zscore  # noqa: E402
from validate_experiment_d import METRICS, WORK, load_questions, metrics  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / 'generated-artifacts' / 'colbert-pack-v1'
SHARD = 1000
METHODS = ('dense', 'weighted_genome', 'weighted_90_10', 'bge_dense_sparse_colbert', 'experiment_d')
# exploratory fusions (dense, sparse, colbert, genome); z-scores over the same candidate union as Experiment D
EXTRA = {
    'ed_g45': (0.18, 0.09, 0.18, 0.45),    # Experiment D's text proportions, genome share raised
    'ed_g60': (0.1371, 0.0686, 0.1371, 0.60),
    'ed_g75': (0.0857, 0.0429, 0.0857, 0.75),
    'blend_g60': (0.10, 0.05, 0.25, 0.60),  # ColBERT-heavier text share
    'blend_g80': (0.05, 0.00, 0.15, 0.80),
    'g80_nocol': (0.10, 0.10, 0.00, 0.80),  # no ColBERT: genome + dense + sparse only
    'g70_nocol': (0.15, 0.15, 0.00, 0.70),
}
ALL_METHODS = METHODS + tuple(EXTRA)


def variant_path(v):
    return FP32 if v == 'fp32' else OUTDIR / f'bge_m3_multi_{v}.onnx'


class Pack:
    def __init__(self, d=PACK):
        n = len(list(d.glob('shard-*.cnt.npy')))
        self.vec = [np.load(d / f'shard-{i:04d}.vec.npy', mmap_mode='r') for i in range(n)]
        self.cum = [np.concatenate([[0], np.cumsum(np.load(d / f'shard-{i:04d}.cnt.npy'))]) for i in range(n)]

    def get(self, row):
        sh, loc = divmod(int(row), SHARD)
        return self.vec[sh][self.cum[sh][loc]:self.cum[sh][loc + 1]]

    def maxsim(self, q, rows):
        """mean over query tokens of max over passage tokens; q [Tq,1024] f32."""
        parts = [self.get(r) for r in rows]
        lens = np.array([len(p) for p in parts])
        sim = q @ np.concatenate(parts, axis=0).astype(np.float32).T
        return np.maximum.reduceat(sim, np.concatenate([[0], np.cumsum(lens)[:-1]]), axis=1).mean(axis=0)


def score_variant(name, s, wg, pack, keys, text, gold, tok, unused):
    t_enc0 = time.perf_counter()
    sess = session(variant_path(name), threads=0)
    dense, sparse, colbert, enc_s = encode(sess, tok, [text[k] for k in keys], unused, batch=16)
    del sess
    vids = s.verse_ids
    out, t_scan, t_col = [], 0.0, 0.0
    for c0 in range(0, len(keys), 100):
        sl = slice(c0, min(c0 + 100, len(keys)))
        t0 = time.perf_counter()
        d = dense[sl]
        Dall = d @ s.dense.T
        g = s.genome_of(d)
        Gall = normalize_rows(g * s.sw) @ wg.T
        qs = sp.lil_matrix((d.shape[0], VOCAB), dtype=np.float32)
        for i, w in enumerate(sparse[sl]):
            for t, x in w.items():
                qs[i, t] = x
        Sall = (s.csr @ qs.tocsr().T).T.toarray()
        t_scan += time.perf_counter() - t0
        for i in range(d.shape[0]):
            qi, (q, lang) = c0 + i, keys[c0 + i]
            da, ga, sa = Dall[i].astype(np.float64), Gall[i].astype(np.float64), Sall[i].astype(np.float64)
            mix = 0.90 * zscore(ga) + 0.10 * zscore(da)
            cand = np.unique(np.concatenate([top_rows(x, vids, 200) for x in (da, sa, ga)]))
            t1 = time.perf_counter()
            zc = zscore(pack.maxsim(colbert[qi], cand))
            t_col += time.perf_counter() - t1
            zd, zs, zg = zscore(da[cand]), zscore(sa[cand]), zscore(ga[cand])
            cv = vids[cand]
            three = 0.40 * zd + 0.20 * zs + 0.40 * zc
            exp_d = SIGNAL_WEIGHTS['dense'] * zd + SIGNAL_WEIGHTS['sparse'] * zs + SIGNAL_WEIGHTS['colbert'] * zc + SIGNAL_WEIGHTS['genome'] * zg
            rk = lambda sc, ids: [int(ids[j]) for j in top_rows(sc, ids, 20)]  # noqa: E731
            out.append({'key': (q, lang), 'm': {
                'dense': metrics(rk(da, vids), gold[q]), 'weighted_genome': metrics(rk(ga, vids), gold[q]),
                'weighted_90_10': metrics(rk(mix, vids), gold[q]),
                'bge_dense_sparse_colbert': metrics(rk(three, cv), gold[q]), 'experiment_d': metrics(rk(exp_d, cv), gold[q]),
                **{n: metrics(rk(w[0] * zd + w[1] * zs + w[2] * zc + w[3] * zg, cv), gold[q]) for n, w in EXTRA.items()},
            }, 'top20_exp_d': rk(exp_d, cv)})
    n = len(keys)
    return out, {'encode_ms_per_query': enc_s / n * 1000, 'scan_ms_per_query': t_scan / n * 1000,
                 'colbert_maxsim_ms_per_query': t_col / n * 1000}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--variants', nargs='+', default=['fp32', 'int8_matmul'])
    ap.add_argument('--limit-qids', type=int, default=0)
    ap.add_argument('--out', default=str(ROOT / 'test' / 'golden' / 'quantization_eval.json'))
    a = ap.parse_args()

    ext = DEFAULT_EXTRACTED
    report = json.loads((ext / 'scripture-genome-question-hidden4096-full' / 'validation_q250.json').read_text('utf-8'))
    qids, langs, text, gold = load_questions(report['manifest'], a.limit_qids)
    keys = [(q, lang) for q in qids for lang in langs]
    s = Searcher(ext, encoder=object())
    with np.load(ext / 'scripture-genome-question-hidden4096-optimized' / 'head_fp16.npz', allow_pickle=False) as z:
        s.head = {'0.weight': z['w0'].astype(np.float32), '0.bias': z['b0'].astype(np.float32),
                  '2.weight': z['w1'].astype(np.float32), '2.bias': z['b1'].astype(np.float32)}
    wg = normalize_rows(np.load(ext / 'scripture-retrieval-english-v1' / 'weighted_genome_embeddings.f16.npy',
                                allow_pickle=False).astype(np.float32))
    tok = AutoTokenizer.from_pretrained(ext / 'bge-m3-pinned')
    unused = {tok.cls_token_id, tok.eos_token_id, tok.pad_token_id, tok.unk_token_id}
    pack = Pack()
    print(f'{len(qids)} q_ids x {len(langs)} langs = {len(keys)} rows; pack shards {len(pack.vec)}', flush=True)

    results, timing = {}, {}
    for v in a.variants:
        cache = WORK / f'eval3-{v}-{len(keys)}.pkl'
        if cache.exists():
            results[v], timing[v] = pickle.load(open(cache, 'rb'))
        else:
            t0 = time.perf_counter()
            results[v], timing[v] = score_variant(v, s, wg, pack, keys, text, gold, tok, unused)
            pickle.dump((results[v], timing[v]), open(cache, 'wb'))
            print(f'{v}: scored in {time.perf_counter() - t0:.0f}s  {timing[v]}', flush=True)

    def per_q(v, method, metric, lang=None):
        by = {r['key']: r['m'][method][metric] for r in results[v]}
        use = [lang] if lang else langs
        return np.array([np.mean([by[(q, l)] for l in use]) for q in qids])

    rng = np.random.default_rng(20261013)
    draws = rng.integers(0, len(qids), size=(2000, len(qids)))
    base = 'fp32'
    summary = {'rows': len(keys), 'timing_ms_per_query': timing, 'variants': {}}
    ref = report['overall_cluster_bootstrap']
    for v in a.variants:
        rec = {'overall': {}, 'by_language_rel_change_experiment_d': {}}
        for method in ALL_METHODS:
            for met in METRICS:
                x = per_q(v, method, met)
                item = {'mean': float(x.mean()), 'packaged_report_mean': ref.get(method, {}).get(met, {}).get('mean')}
                if v != base and base in results:
                    b = per_q(base, method, met)
                    diff = x - b
                    lo, hi = np.percentile(diff[draws].mean(axis=1), [2.5, 97.5])
                    item.update({'fp32_mean': float(b.mean()), 'delta': float(diff.mean()), 'delta_ci95': [float(lo), float(hi)],
                                 'rel_change_pct': float(100 * diff.mean() / b.mean()) if b.mean() else None})
                rec['overall'][f'{method}/{met}'] = item
        if v != base and base in results:
            for lang in langs:
                for met in ('recall@10', 'weighted_ndcg@20'):
                    x, b = per_q(v, 'experiment_d', met, lang).mean(), per_q(base, 'experiment_d', met, lang).mean()
                    rec['by_language_rel_change_experiment_d'][f'{lang}/{met}'] = float(100 * (x - b) / b)
            r10 = rec['overall']['experiment_d/recall@10']['rel_change_pct']
            nd = rec['overall']['experiment_d/weighted_ndcg@20']['rel_change_pct']
            worst = min(rec['by_language_rel_change_experiment_d'].values())
            rec['gate'] = {'recall@10_rel_pct': r10, 'ndcg@20_rel_pct': nd, 'worst_language_rel_pct': worst,
                           'pass_overall_2pct': bool(r10 >= -2 and nd >= -2), 'pass_language_5pct': bool(worst >= -5)}
        summary['variants'][v] = rec
        print(f'\n== {v}')
        for method in ALL_METHODS:
            row = rec['overall'][f'{method}/recall@10'], rec['overall'][f'{method}/weighted_ndcg@20']
            extra = ''
            if 'rel_change_pct' in row[0]:
                extra = f"  vs fp32: R@10 {row[0]['rel_change_pct']:+.2f}%  nDCG {row[1]['rel_change_pct']:+.2f}%"
            rep = lambda r: f'{r["packaged_report_mean"]:.4f}' if r['packaged_report_mean'] is not None else '  n/a '  # noqa: E731
            print(f'  {method:26s} R@10 {row[0]["mean"]:.4f} (report {rep(row[0])})  '
                  f'nDCG@20 {row[1]["mean"]:.4f} (report {rep(row[1])}){extra}')
        if 'gate' in rec:
            print('  GATE', rec['gate'])
    Path(a.out).write_text(json.dumps(summary, indent=1), 'utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
