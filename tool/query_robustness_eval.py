"""How much does WORDING matter? Compare retrieval methods across many ways of asking the same thing.

For each intent in tool/query_robustness_set.json (8 phrasings: formal, casual, keyword, single word, synonym,
long personal narrative, typo, another language) this runs the deployment-shaped pipeline (ONNX query encoder ->
shipped index -> ColBERT pack) and reports, per method and per wording kind:
  hit@5 / hit@10 / MRR@10 against well-known anchor passages (tool/seeker_scenarios.json), and
  stability: how similar the top-10 stays across paraphrases of the same intent (Jaccard), no anchors needed.

Methods: dense, genome (genome only), weighted_90_10, bge3 (dense+sparse+colbert), experiment_d, and two exploratory
genome-heavy blends. Everything runs on the same candidate union as Experiment D where a fusion is involved.

  .venv\\Scripts\\python.exe -I tool/query_robustness_eval.py --variants int8_matmul_gather [fp32]
"""
import argparse
import itertools
import json
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
from scipy import sparse as sp

sys.path.insert(0, str(Path(__file__).resolve().parent))
from e2e_scenarios import Engine  # noqa: E402
from eval_quantized import variant_path  # noqa: E402,F401
from quantize_onnx import encode  # noqa: E402
from reference_search import VOCAB, normalize_rows, top_rows, zscore  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
# references are identical in every edition; the pinned base carries them as a column
RELEASE = ROOT / '.artifact-staging' / 'import-application-v1' / 'databases' / 'scriptures_genome.db'
# (dense, sparse, colbert, genome)
FUSIONS = {
    'bge3': (0.40, 0.20, 0.40, 0.00),
    'experiment_d': (0.28, 0.14, 0.28, 0.30),
    'blend_g60': (0.10, 0.05, 0.25, 0.60),
    'blend_g80': (0.05, 0.00, 0.15, 0.80),
    'ed_g75': (0.0857, 0.0429, 0.0857, 0.75),
    'g80_nocol': (0.10, 0.10, 0.00, 0.80),
    'g70_nocol': (0.15, 0.15, 0.00, 0.70),
}
METHODS = ('dense', 'genome', 'weighted_90_10', 'bge3', 'experiment_d', 'blend_g60', 'blend_g80', 'ed_g75', 'g80_nocol', 'g70_nocol')
KINDS = ('formal', 'casual', 'keyword', 'single', 'synonym', 'narrative', 'typo', 'other')
ENGLISH_KINDS = ('formal', 'casual', 'keyword', 'synonym', 'narrative', 'typo')


def rank_all(eng, query, k=20):
    s, vids = eng.s, eng.s.verse_ids
    dense, sparse, col, _ = encode(eng.sess, eng.tok, [query], eng.unused, batch=1)
    d = dense[0]
    da = (s.dense @ d).astype(np.float64)
    ga = (eng.wg @ normalize_rows((s.genome_of(d) * s.sw)[None, :])[0]).astype(np.float64)
    qs = sp.lil_matrix((1, VOCAB), dtype=np.float32)
    for t, x in sparse[0].items():
        qs[0, t] = x
    sa = (s.csr @ qs.tocsr().T).toarray().ravel().astype(np.float64)
    cand = np.unique(np.concatenate([top_rows(x, vids, 200) for x in (da, sa, ga)]))
    zc = zscore(eng.pack.maxsim(col[0], cand))
    zd, zs, zg = zscore(da[cand]), zscore(sa[cand]), zscore(ga[cand])
    cv = vids[cand]
    top = lambda sc, ids: [int(ids[i]) for i in top_rows(sc, ids, k)]  # noqa: E731
    out = {'dense': top(da, vids), 'genome': top(ga, vids),
           'weighted_90_10': top(0.9 * zscore(ga) + 0.1 * zscore(da), vids)}
    for name, (wd, ws, wc, wg) in FUSIONS.items():
        out[name] = top(wd * zd + ws * zs + wc * zc + wg * zg, cv)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--variants', nargs='+', default=['int8_matmul_gather'])
    ap.add_argument('--limit', type=int, default=0, help='first N intents only (smoke test)')
    a = ap.parse_args()

    data = json.loads((ROOT / 'tool' / 'query_robustness_set.json').read_text('utf-8'))
    scen = {x['id']: x['anchors'] for x in json.loads((ROOT / 'tool' / 'seeker_scenarios.json').read_text('utf-8'))['scenarios']}
    c = sqlite3.connect(f'file:{RELEASE.as_posix()}?mode=ro', uri=True)
    ref_of = dict(c.execute('SELECT verse_id, reference FROM scriptures_english'))
    intents = data['intents'][:a.limit] if a.limit else data['intents']

    def hit(ref, anchors):
        return any(ref == an or (an.endswith(':*') and ref.startswith(an[:-1])) for an in anchors)

    eng = Engine()
    for variant in a.variants:
        eng.use(variant)
        eng.search('warm up')
        t0 = time.perf_counter()
        results = {}  # (intent, kind) -> {method: [verse ids]}
        n = 0
        for it in intents:
            for kind in KINDS:
                v = it['variants'][kind]
                text = v['text'] if isinstance(v, dict) else v
                results[(it['id'], kind)] = rank_all(eng, text)
                n += 1
        secs = time.perf_counter() - t0
        print(f'\n=== encoder variant: {variant} | {n} queries in {secs:.0f}s ({secs / n * 1000:.0f} ms/query incl. all methods)')

        # ---- anchor metrics by wording kind ------------------------------------------------------------------------
        def metric(method, kind, fn):
            vals = []
            for it in intents:
                anchors = scen[it['anchors_from']]
                top = [ref_of[i] for i in results[(it['id'], kind)][method][:10]]
                vals.append(fn(top, anchors))
            return float(np.mean(vals))

        h10 = lambda top, an: float(any(hit(r, an) for r in top))                                   # noqa: E731
        h5 = lambda top, an: float(any(hit(r, an) for r in top[:5]))                                 # noqa: E731
        mrr = lambda top, an: next((1.0 / (i + 1) for i, r in enumerate(top) if hit(r, an)), 0.0)    # noqa: E731
        print('\nhit@10 by wording kind (share of intents with at least one anchor passage in the top 10)')
        print(f'{"method":16s}' + ''.join(f'{k:>10s}' for k in KINDS) + f'{"ALL":>8s}')
        summary = {}
        for m in METHODS:
            row = [metric(m, k, h10) for k in KINDS]
            summary[m] = {'hit@10': dict(zip(KINDS, row)), 'hit@10_all': float(np.mean(row)),
                          'hit@5_all': float(np.mean([metric(m, k, h5) for k in KINDS])),
                          'mrr@10_all': float(np.mean([metric(m, k, mrr) for k in KINDS]))}
            print(f'{m:16s}' + ''.join(f'{x:10.2f}' for x in row) + f'{np.mean(row):8.2f}')
        print('\nhit@5 / MRR@10 over all wordings')
        for m in METHODS:
            print(f'  {m:16s} hit@5 {summary[m]["hit@5_all"]:.2f}   MRR@10 {summary[m]["mrr@10_all"]:.2f}')

        # ---- stability across paraphrases ---------------------------------------------------------------------------
        def jac(x, y):
            x, y = set(x), set(y)
            return len(x & y) / len(x | y) if x | y else 1.0

        print('\nstability: how much the top-10 stays the same when only the wording changes (1.0 = identical)')
        print(f'{"method":16s}{"English paraphrases":>22s}{"other language vs formal":>28s}')
        for m in METHODS:
            eng_j, xl = [], []
            for it in intents:
                tops = {k: results[(it['id'], k)][m][:10] for k in KINDS}
                eng_j += [jac(tops[p], tops[q]) for p, q in itertools.combinations(ENGLISH_KINDS, 2)]
                xl.append(jac(tops['other'], tops['formal']))
            summary[m]['stability_english'] = float(np.mean(eng_j))
            summary[m]['stability_cross_language'] = float(np.mean(xl))
            print(f'{m:16s}{np.mean(eng_j):22.2f}{np.mean(xl):28.2f}')

        # ---- where each method fails ---------------------------------------------------------------------------------
        print('\nintents with NO anchor in the top 10, by method (wording kinds that failed)')
        for m in ('weighted_90_10', 'experiment_d'):
            bad = []
            for it in intents:
                ks = [k for k in KINDS if not h10([ref_of[i] for i in results[(it['id'], k)][m][:10]], scen[it['anchors_from']])]
                if len(ks) >= 4:
                    bad.append(f"{it['id']}({len(ks)}/8)")
            print(f'  {m:16s} {", ".join(bad) if bad else "none"}')

        out = {'variant': variant, 'summary': summary, 'queries': {
            f'{iid}|{kind}': {m: [ref_of[i] for i in ids[:10]] for m, ids in per.items()} for (iid, kind), per in results.items()}}
        path = ROOT / 'test' / 'golden' / f'query_robustness_{variant}.json'
        path.write_text(json.dumps(out, indent=1, ensure_ascii=False), 'utf-8')
        print('\nwrote', path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
