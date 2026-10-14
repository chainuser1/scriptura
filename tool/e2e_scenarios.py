"""End-to-end "seeker" evaluation: realistic gospel-learning questions through the DEPLOYMENT-SHAPED pipeline.

Query encoder = ONNX Runtime variant (as on-device) -> shipped FP32 dense/sparse/genome index -> offline FP16
ColBERT pack -> Experiment D fusion. Compares methods (dense, weighted_90_10, experiment_d) and variants (fp32 vs INT8)
on tool/seeker_scenarios.json, with anchor hit-rates, top-k overlap between variants, latency and edge behavior.

Committed output has verse REFERENCES only; passage text goes to gitignored local-benchmarks/.

  .venv\\Scripts\\python.exe -I tool/e2e_scenarios.py --variants fp32 int8_matmul_gather
"""
import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
from scipy import sparse as sp
from transformers import AutoTokenizer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_quantized import Pack, variant_path  # noqa: E402
from quantize_onnx import encode, session  # noqa: E402
from reference_search import DEFAULT_EXTRACTED, SIGNAL_WEIGHTS, VOCAB, Searcher, normalize_rows, top_rows, zscore  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
IMPORT = DEFAULT_EXTRACTED.parent
METHODS = ('dense', 'weighted_90_10', 'experiment_d')


class Engine:
    def __init__(self, ext=DEFAULT_EXTRACTED):
        self.s = Searcher(ext, encoder=object())
        with np.load(ext / 'scripture-genome-question-hidden4096-optimized' / 'head_fp16.npz', allow_pickle=False) as z:
            self.s.head = {'0.weight': z['w0'].astype(np.float32), '0.bias': z['b0'].astype(np.float32),
                           '2.weight': z['w1'].astype(np.float32), '2.bias': z['b1'].astype(np.float32)}
        self.wg = normalize_rows(np.load(ext / 'scripture-retrieval-english-v1' / 'weighted_genome_embeddings.f16.npy',
                                         allow_pickle=False).astype(np.float32))
        self.tok = AutoTokenizer.from_pretrained(ext / 'bge-m3-pinned')
        self.unused = {self.tok.cls_token_id, self.tok.eos_token_id, self.tok.pad_token_id, self.tok.unk_token_id}
        self.pack = Pack()
        self.sess = None

    def use(self, variant):
        self.sess = session(variant_path(variant))

    def search(self, query):
        s, vids = self.s, self.s.verse_ids
        if not query.strip():
            return {'status': 'invalid_input', 'reason': 'empty'}
        n_tok = len(self.tok(query, truncation=False)['input_ids'])
        if n_tok > 512:
            return {'status': 'invalid_input', 'reason': f'{n_tok} tokens > 512'}
        t0 = time.perf_counter()
        dense, sparse, col, _ = encode(self.sess, self.tok, [query], self.unused, batch=1)
        t1 = time.perf_counter()
        d = dense[0]
        da = (s.dense @ d).astype(np.float64)
        ga = (self.wg @ normalize_rows((s.genome_of(d) * s.sw)[None, :])[0]).astype(np.float64)
        qs = sp.lil_matrix((1, VOCAB), dtype=np.float32)
        for t, x in sparse[0].items():
            qs[0, t] = x
        sa = (s.csr @ qs.tocsr().T).toarray().ravel().astype(np.float64)
        cand = np.unique(np.concatenate([top_rows(x, vids, 200) for x in (da, sa, ga)]))
        t2 = time.perf_counter()
        zc = zscore(self.pack.maxsim(col[0], cand))
        t3 = time.perf_counter()
        zd, zs, zg = zscore(da[cand]), zscore(sa[cand]), zscore(ga[cand])
        exp_d = SIGNAL_WEIGHTS['dense'] * zd + SIGNAL_WEIGHTS['sparse'] * zs + SIGNAL_WEIGHTS['colbert'] * zc + SIGNAL_WEIGHTS['genome'] * zg
        mix = 0.90 * zscore(ga) + 0.10 * zscore(da)
        cv = vids[cand]
        rk = lambda sc, ids: [int(ids[j]) for j in top_rows(sc, ids, 20)]  # noqa: E731
        return {'status': 'ok', 'tokens': n_tok, 'candidates': int(len(cand)),
                'rank': {'dense': rk(da, vids), 'weighted_90_10': rk(mix, vids), 'experiment_d': rk(exp_d, cv)},
                'ms': {'encode': (t1 - t0) * 1000, 'scan_and_lanes': (t2 - t1) * 1000, 'colbert_maxsim': (t3 - t2) * 1000,
                       'total': (time.perf_counter() - t0) * 1000}}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--variants', nargs='+', default=['fp32', 'int8_matmul_gather'])
    ap.add_argument('--out', default=str(ROOT / 'test' / 'golden' / 'e2e_seeker_eval.json'))
    a = ap.parse_args()

    sc = json.loads((ROOT / 'tool' / 'seeker_scenarios.json').read_text('utf-8'))['scenarios']
    c = sqlite3.connect(f'file:{(IMPORT / "databases" / "scriptures_genome.db").as_posix()}?mode=ro', uri=True)
    ref_of = {v: r for v, r in c.execute('SELECT verse_id, reference FROM scriptures_english')}
    text_of = dict(c.execute('SELECT verse_id, scripture_text FROM scriptures_english'))
    refs = set(ref_of.values())
    unresolved = [(x['id'], an) for x in sc for an in x['anchors'] if not an.endswith(':*') and an not in refs]
    if unresolved:
        print('UNRESOLVED ANCHORS (authoring errors):', unresolved)

    def hit(ref, anchors):
        return any(ref == an or (an.endswith(':*') and ref.startswith(an[:-1])) for an in anchors)

    eng = Engine()
    out = {'variants': {}, 'unresolved_anchors': unresolved}
    local = {}
    for v in a.variants:
        eng.use(v)
        eng.search('warm up the session')
        rows = []
        for x in sc:
            r = eng.search(x['query'])
            row = {'id': x['id'], 'category': x['category'], 'query': x['query'], 'status': r['status']}
            if r['status'] == 'ok':
                row.update({'tokens': r['tokens'], 'candidates': r['candidates'], 'ms': r['ms'], 'methods': {}})
                for m in METHODS:
                    top = [ref_of[i] for i in r['rank'][m]]
                    anchors = x['anchors']
                    row['methods'][m] = {
                        'top10': top[:10],
                        'hit@5': any(hit(t, anchors) for t in top[:5]) if anchors else None,
                        'hit@10': any(hit(t, anchors) for t in top[:10]) if anchors else None,
                        'anchors_found@10': sum(any(hit(t, [an]) for t in top[:10]) for an in anchors) if anchors else None,
                        'n_anchors': len(anchors)}
                local.setdefault(v, {})[x['id']] = {m: [{'ref': ref_of[i], 'text': text_of[i]} for i in r['rank'][m][:10]] for m in METHODS}
            else:
                row['reason'] = r['reason']
            rows.append(row)
        out['variants'][v] = rows
        ok = [r for r in rows if r['status'] == 'ok']
        print(f'{v}: {len(ok)}/{len(rows)} ok | median total {np.median([r["ms"]["total"] for r in ok]):.0f} ms '
              f'(encode {np.median([r["ms"]["encode"] for r in ok]):.0f}, colbert {np.median([r["ms"]["colbert_maxsim"] for r in ok]):.0f})',
              flush=True)

    Path(a.out).write_text(json.dumps(out, indent=1, ensure_ascii=False), 'utf-8')
    bench = ROOT / 'local-benchmarks'
    bench.mkdir(exist_ok=True)
    (bench / 'e2e_seeker_with_text.json').write_text(json.dumps(local, indent=1, ensure_ascii=False), 'utf-8')

    # console summary
    for v in a.variants:
        rows = [r for r in out['variants'][v] if r['status'] == 'ok' and r['methods']['experiment_d']['n_anchors']]
        print(f'\n== {v}  (scenarios with anchors: {len(rows)})')
        for m in METHODS:
            h5 = np.mean([r['methods'][m]['hit@5'] for r in rows])
            h10 = np.mean([r['methods'][m]['hit@10'] for r in rows])
            rec = np.mean([r['methods'][m]['anchors_found@10'] / min(r['methods'][m]['n_anchors'], 10) for r in rows])
            print(f'  {m:16s} hit@5 {h5:.2f}  hit@10 {h10:.2f}  anchor-recall@10 {rec:.2f}')
        cats = sorted({r['category'] for r in rows})
        print('  experiment_d hit@10 by category:', {c_: round(float(np.mean([r['methods']['experiment_d']['hit@10'] for r in rows if r['category'] == c_])), 2) for c_ in cats})
    if len(a.variants) == 2:
        A, B = (out['variants'][v] for v in a.variants)
        ov = [len(set(x['methods']['experiment_d']['top10']) & set(y['methods']['experiment_d']['top10'])) / 10
              for x, y in zip(A, B) if x['status'] == 'ok' and y['status'] == 'ok']
        print(f'\ntop-10 overlap {a.variants[0]} vs {a.variants[1]} (experiment_d): mean {np.mean(ov):.2f}, min {np.min(ov):.1f}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
