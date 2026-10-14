"""Systematic search over ways to combine the four retrieval signals (dense, sparse, ColBERT, genome).

Step 1 (slow, once): cache the per-query signal arrays over the Experiment-D candidate union, for
  (a) the 250 q_id x 8 language labeled benchmark (2,000 rows) and
  (b) the 192-query wording set (tool/query_robustness_set.json).
Step 2 (seconds): evaluate any combination offline: weighted z-score sums over a simplex grid, reciprocal-rank
fusion, and two-lane interleaving; report top combinations on each set, a robust (worst-of-both) ranking, and a
two-fold held-out check so picks are not just fitted noise.

  .venv\\Scripts\\python.exe -I tool/fusion_search.py [--rebuild] [--variant int8_matmul]
"""
import argparse
import itertools
import json
import pickle
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
from reference_search import DEFAULT_EXTRACTED, VOCAB, Searcher, normalize_rows, top_rows, zscore  # noqa: E402
from validate_experiment_d import load_questions, metrics  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / '.artifact-staging' / 'validation'
SIGNALS = ('dense', 'sparse', 'colbert', 'genome')
KINDS = ('formal', 'casual', 'keyword', 'single', 'synonym', 'narrative', 'typo', 'other')


# ---------------------------------------------------------------- step 1: signal cache -------------------------------
def signals_for(texts, variant, batch=16):
    s = Searcher(DEFAULT_EXTRACTED, encoder=object())
    with np.load(DEFAULT_EXTRACTED / 'scripture-genome-question-hidden4096-optimized' / 'head_fp16.npz', allow_pickle=False) as z:
        s.head = {'0.weight': z['w0'].astype(np.float32), '0.bias': z['b0'].astype(np.float32),
                  '2.weight': z['w1'].astype(np.float32), '2.bias': z['b1'].astype(np.float32)}
    wg = normalize_rows(np.load(DEFAULT_EXTRACTED / 'scripture-retrieval-english-v1' / 'weighted_genome_embeddings.f16.npy',
                                allow_pickle=False).astype(np.float32))
    tok = AutoTokenizer.from_pretrained(DEFAULT_EXTRACTED / 'bge-m3-pinned')
    unused = {tok.cls_token_id, tok.eos_token_id, tok.pad_token_id, tok.unk_token_id}
    pack, sess, vids = Pack(), session(variant_path(variant)), s.verse_ids
    dense, sparse, col, _ = encode(sess, tok, texts, unused, batch=batch)
    out = []
    for c0 in range(0, len(texts), 100):
        sl = slice(c0, min(c0 + 100, len(texts)))
        d = dense[sl]
        Dall = d @ s.dense.T
        Gall = normalize_rows(s.genome_of(d) * s.sw) @ wg.T
        qs = sp.lil_matrix((d.shape[0], VOCAB), dtype=np.float32)
        for i, w in enumerate(sparse[sl]):
            for t, x in w.items():
                qs[i, t] = x
        Sall = (s.csr @ qs.tocsr().T).T.toarray()
        for i in range(d.shape[0]):
            da, ga, sa = (x.astype(np.float64) for x in (Dall[i], Gall[i], Sall[i]))
            cand = np.unique(np.concatenate([top_rows(x, vids, 200) for x in (da, sa, ga)]))
            ca = pack.maxsim(col[c0 + i], cand)
            r9010 = vids[top_rows(0.9 * zscore(ga) + 0.1 * zscore(da), vids, 20)]
            out.append({'ids': vids[cand].astype(np.int32),
                        'raw': np.stack([da[cand], sa[cand], ca, ga[cand]]).astype(np.float32),
                        'r9010': r9010.astype(np.int32)})
    return out


def build_caches(variant):
    report = json.loads((DEFAULT_EXTRACTED / 'scripture-genome-question-hidden4096-full' / 'validation_q250.json').read_text('utf-8'))
    qids, langs, text, gold = load_questions(report['manifest'], 0)
    keys = [(q, l) for q in qids for l in langs]
    t = time.perf_counter()
    bench = signals_for([text[k] for k in keys], variant)
    print(f'benchmark signals: {len(keys)} rows in {time.perf_counter() - t:.0f}s', flush=True)
    data = json.loads((ROOT / 'tool' / 'query_robustness_set.json').read_text('utf-8'))
    wkeys, wtexts = [], []
    for it in data['intents']:
        for k in KINDS:
            v = it['variants'][k]
            wkeys.append((it['id'], k))
            wtexts.append(v['text'] if isinstance(v, dict) else v)
    t = time.perf_counter()
    word = signals_for(wtexts, variant, batch=1)
    print(f'wording signals: {len(wkeys)} queries in {time.perf_counter() - t:.0f}s', flush=True)
    pickle.dump({'bench': (keys, bench, gold), 'word': (wkeys, word)}, open(CACHE / f'signals-{variant}.pkl', 'wb'))


# ---------------------------------------------------------------- step 2: offline evaluation -----------------------------
def zrows(rows):
    for r in rows:
        r['Z'] = np.stack([zscore(r['raw'][k]) for k in range(4)])
        r['ord_id'] = r['ids']
    return rows


def rank_weights(r, w, k=20):
    sc = w @ r['Z']
    return r['ids'][np.lexsort((r['ids'], -sc))[:k]]


def rank_lists_from(r, k=20):
    return [r['ids'][np.lexsort((r['ids'], -r['Z'][i]))[:k]] for i in range(4)]


def rrf(lists, weights=None, k0=60, k=20):
    score = {}
    for li, lst in enumerate(lists):
        for rank, v in enumerate(lst):
            score[int(v)] = score.get(int(v), 0.0) + (1.0 if weights is None else weights[li]) / (k0 + rank + 1)
    return np.array(sorted(score, key=lambda v: (-score[v], v))[:k])


def interleave(a, b, k=20):
    out, seen = [], set()
    for x, y in itertools.zip_longest(a, b):
        for v in (x, y):
            if v is not None and int(v) not in seen:
                seen.add(int(v))
                out.append(int(v))
    return np.array(out[:k])


def grid(step=0.1):
    n = int(round(1 / step))
    return [np.array(c) * step for c in itertools.product(range(n + 1), repeat=4) if sum(c) == n]


class Evaluator:
    def __init__(self, bench, word, ref_of, anchors):
        self.keys, self.rows, self.gold = bench[0], zrows(bench[1]), bench[2]
        self.qids = sorted({k[0] for k in self.keys})
        self.q_index = {q: i for i, q in enumerate(self.qids)}
        self.wkeys, self.wrows = word[0], zrows(word[1])
        self.ref_of, self.anchors = ref_of, anchors
        self.intents = sorted({k[0] for k in self.wkeys})

    def hit(self, ids, anchors, k=10):
        refs = [self.ref_of[int(i)] for i in ids[:k]]
        return float(any(r == a or (a.endswith(':*') and r.startswith(a[:-1])) for r in refs for a in anchors))

    def bench_score(self, ranker, q_subset=None):
        by_q = {}
        for key, r in zip(self.keys, self.rows):
            if q_subset is not None and key[0] not in q_subset:
                continue
            m = metrics([int(x) for x in ranker(r)], self.gold[key[0]])
            by_q.setdefault(key[0], []).append((m['recall@10'], m['weighted_ndcg@20']))
        a = np.array([np.mean(v, axis=0) for v in by_q.values()])
        return float(a[:, 0].mean()), float(a[:, 1].mean())

    def word_score(self, ranker, intent_subset=None):
        hits = []
        for (iid, kind), r in zip(self.wkeys, self.wrows):
            if intent_subset is not None and iid not in intent_subset:
                continue
            hits.append(self.hit(ranker(r), self.anchors[iid]))
        return float(np.mean(hits))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--variant', default='int8_matmul')
    ap.add_argument('--rebuild', action='store_true')
    ap.add_argument('--step', type=float, default=0.1)
    a = ap.parse_args()
    cache = CACHE / f'signals-{a.variant}.pkl'
    if a.rebuild or not cache.exists():
        build_caches(a.variant)
    blob = pickle.load(open(cache, 'rb'))

    c = sqlite3.connect(f'file:{(DEFAULT_EXTRACTED.parent / "databases" / "scriptures_genome.db").as_posix()}?mode=ro', uri=True)
    ref_of = dict(c.execute('SELECT verse_id, reference FROM scriptures_english'))
    scen = {x['id']: x['anchors'] for x in json.loads((ROOT / 'tool' / 'seeker_scenarios.json').read_text('utf-8'))['scenarios']}
    intents = json.loads((ROOT / 'tool' / 'query_robustness_set.json').read_text('utf-8'))['intents']
    anchors = {it['id']: scen[it['anchors_from']] for it in intents}
    ev = Evaluator(blob['bench'], blob['word'], ref_of, anchors)

    named = {
        'experiment_d': np.array([0.28, 0.14, 0.28, 0.30]), '90:10 (full-corpus z)': None,
        'lean g80_nocol': np.array([0.10, 0.10, 0.0, 0.80]), 'full blend_g80': np.array([0.05, 0.0, 0.15, 0.80]),
    }
    results = []   # (label, weights or None, bench R@10, bench nDCG, wording hit@10)

    def add(label, ranker, w=None):
        b = ev.bench_score(ranker)
        results.append((label, w, b[0], b[1], ev.word_score(ranker)))

    add('experiment_d', lambda r: rank_weights(r, named['experiment_d']), named['experiment_d'])
    add('90:10 (full-corpus z)', lambda r: r['r9010'])
    add('lean g80_nocol', lambda r: rank_weights(r, named['lean g80_nocol']), named['lean g80_nocol'])
    add('full blend_g80', lambda r: rank_weights(r, named['full blend_g80']), named['full blend_g80'])
    # structure-different combinations
    text = np.array([0.4, 0.2, 0.4, 0.0])
    gen = np.array([0.0, 0.0, 0.0, 1.0])
    add('RRF(text, genome)', lambda r: rrf([rank_weights(r, text), rank_weights(r, gen)]))
    add('RRF(dense, colbert, genome)', lambda r: rrf([rank_lists_from(r)[0], rank_lists_from(r)[2], rank_lists_from(r)[3]]))
    add('RRF(all four signals)', lambda r: rrf(rank_lists_from(r)))
    add('RRF(dense+colbert, genome) 1:2', lambda r: rrf([rank_weights(r, np.array([.5, 0, .5, 0])), rank_weights(r, gen)], weights=[1, 2]))
    add('two-lane: text then genome', lambda r: interleave(rank_weights(r, text), rank_weights(r, gen)))
    add('two-lane: genome then text', lambda r: interleave(rank_weights(r, gen), rank_weights(r, text)))
    # duos
    for i, j in itertools.combinations(range(4), 2):
        for share in (0.5, 0.7, 0.85):
            w = np.zeros(4)
            w[j], w[i] = share, 1 - share
            add(f'duo {SIGNALS[j]} {share:.2f} + {SIGNALS[i]} {1 - share:.2f}', lambda r, w=w: rank_weights(r, w), w)
    # full simplex grid
    for w in grid(a.step):
        add('grid ' + '/'.join(f'{x:.2f}' for x in w), lambda r, w=w: rank_weights(r, w), w)

    best_b = max(r[2] for r in results)
    best_w = max(r[4] for r in results)
    rob = lambda r: min(r[2] / best_b, r[4] / best_w)  # noqa: E731
    print(f'\n{len(results)} combinations evaluated | best benchmark R@10 {best_b:.4f}, best wording hit@10 {best_w:.3f}')
    hdr = f'{"combination":44s}{"bench R@10":>11s}{"nDCG@20":>9s}{"wording":>9s}{"robust":>8s}'
    show = lambda rs: [print(f'{r[0]:44s}{r[2]:11.4f}{r[3]:9.4f}{r[4]:9.3f}{rob(r):8.3f}') for r in rs]  # noqa: E731
    print('\nreference points'); print(hdr); show(results[:4])
    print('\nstructurally different combinations (rank fusion, two lanes) and duos'); print(hdr)
    show([r for r in results if not r[0].startswith('grid') and r[0] not in named])
    print('\ntop 8 on the labeled benchmark'); print(hdr); show(sorted(results, key=lambda r: -r[2])[:8])
    print('\ntop 8 on the wording set'); print(hdr); show(sorted(results, key=lambda r: -r[4])[:8])
    print('\ntop 10 by ROBUSTNESS (worst of the two sets, each relative to its own best)'); print(hdr)
    show(sorted(results, key=lambda r: -rob(r))[:10])

    # two-fold held-out: choose on one half, evaluate on the other
    print('\nheld-out check (choose by robustness on half A, report on half B; and the reverse)')
    qh = [set(ev.qids[0::2]), set(ev.qids[1::2])]
    ih = [set(ev.intents[0::2]), set(ev.intents[1::2])]
    cands = [(r[0], r[1]) for r in results if r[1] is not None or r[0] in ('90:10 (full-corpus z)',)]
    for tr, te in ((0, 1), (1, 0)):
        scored = []
        for label, w in cands:
            ranker = (lambda r: r['r9010']) if w is None else (lambda r, w=w: rank_weights(r, w))
            b = ev.bench_score(ranker, qh[tr])[0]
            wd = ev.word_score(ranker, ih[tr])
            scored.append((label, w, b, wd))
        bb, ww = max(s[2] for s in scored), max(s[3] for s in scored)
        pick = max(scored, key=lambda s: min(s[2] / bb, s[3] / ww))
        ranker = (lambda r: r['r9010']) if pick[1] is None else (lambda r, w=pick[1]: rank_weights(r, w))
        ref = lambda r: rank_weights(r, named['experiment_d'])  # noqa: E731
        print(f'  pick on half {"AB"[tr]}: {pick[0]:36s} -> half {"AB"[te]} bench R@10 {ev.bench_score(ranker, qh[te])[0]:.4f} '
              f'wording {ev.word_score(ranker, ih[te]):.3f}   | Experiment D there: R@10 {ev.bench_score(ref, qh[te])[0]:.4f} '
              f'wording {ev.word_score(ref, ih[te]):.3f}')
    out = ROOT / 'test' / 'golden' / f'fusion_search_{a.variant}.json'
    out.write_text(json.dumps([{'combination': r[0], 'weights': None if r[1] is None else [float(x) for x in r[1]],
                                'bench_recall10': r[2], 'bench_ndcg20': r[3], 'wording_hit10': r[4]} for r in results],
                              indent=1), 'utf-8')
    print('\nwrote', out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
