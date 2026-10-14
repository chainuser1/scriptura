"""Does a topic-overlap signal improve "similar verses"? Local evaluation only; nothing here ships.

Signal T: tf-idf cosine over the verse -> topic incidence of an independent human-made index (Topical Guide, TG, or the
Triple Combination index, TI). Baseline G: the engine's similar-verses profile (cosine of weighted genome vectors).
Fusion F: z-score fusion over the union of both candidate lists, as the search engine fuses lanes.

Two truths with opposite biases, so a win on both is robust:
  A. question co-targets: verses mapped to the same study question (genome is built from this source -> biased FOR G);
  B. the OTHER topic index: verses sharing a topic in TI when T comes from TG, and vice versa (biased FOR T, softly:
     both are Church indexes but compiled separately).
Metrics per source verse over its positives: precision@10, recall@20, nDCG@10; paired bootstrap interval of F - G.

  .venv\\Scripts\\python.exe -I tool/topic_signal_eval.py [--sources 1500]
"""
import argparse
import json
import math
import random
import sqlite3
import sys
from pathlib import Path

import numpy as np
import scipy.sparse as sp

ROOT = Path(__file__).resolve().parent.parent
BACKUP = ROOT.parent / 'scriptura' / 'app-backups' / 'scriptures_reader_mobile-before-phase0-20261011' / 'assets' / 'resources' / 'db'
APPDB = ROOT.parent / 'scriptura' / 'application_databases'
RET = ROOT / 'generated-artifacts' / 'engine-pack' / 'retrieval'


def incidence(db, vindex):
    c = sqlite3.connect(f'file:{(BACKUP / db).as_posix()}?mode=ro&immutable=1', uri=True)
    topics, rows, cols = {}, [], []
    for slug, v in c.execute('SELECT topic_slug, verse_id FROM topic_verse_index'):
        if v in vindex:
            rows.append(vindex[v])
            cols.append(topics.setdefault(slug, len(topics)))
    m = sp.csr_matrix((np.ones(len(rows), dtype=np.float32), (rows, cols)), shape=(len(vindex), len(topics)))
    m.data[:] = 1.0
    return m


def tfidf(m):
    df = np.asarray((m > 0).sum(axis=0)).ravel()
    idf = np.log((m.shape[0] + 1) / (df + 1)) + 1
    w = m.multiply(idf).tocsr()
    norm = np.sqrt(np.asarray(w.multiply(w).sum(axis=1)).ravel()).clip(1e-9)
    return sp.diags(1 / norm) @ w


def z(x):
    s = x.std()
    return (x - x.mean()) / s if s > 0 else x * 0


def metrics(ranked, positives):
    top10 = ranked[:10]
    hit = [r in positives for r in top10]
    dcg = sum(1 / math.log2(i + 2) for i, h in enumerate(hit) if h)
    idcg = sum(1 / math.log2(i + 2) for i in range(min(10, len(positives))))
    return {'p10': sum(hit) / 10, 'r20': len(set(ranked[:20]) & positives) / len(positives), 'ndcg': dcg / idcg if idcg else 0.0}


def boot(a, b, rng, n=1000):
    d = [x - y for x, y in zip(a, b)]
    m = sum(d) / len(d)
    bs = sorted(sum(d[rng.randrange(len(d))] for _ in d) / len(d) for _ in range(n))
    return m, bs[int(n * 0.025)], bs[int(n * 0.975)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--sources', type=int, default=1500)
    ap.add_argument('--weight', type=float, default=0.5, help='topic weight in the fusion (genome weight 1.0)')
    a = ap.parse_args()
    rng = random.Random(4)

    vids = np.load(RET / 'verse_ids.npy')
    G = np.load(RET / 'weighted_genome_embeddings.f16.npy').astype(np.float32)
    vindex = {int(v): i for i, v in enumerate(vids)}
    TG = tfidf(incidence('topical-guide.db', vindex))
    TI = tfidf(incidence('triple-index.db', vindex))
    TGb, TIb = (TG > 0).astype(np.float32), (TI > 0).astype(np.float32)
    print(f'TG covers {int((TG.getnnz(axis=1) > 0).sum())} verses, TI covers {int((TI.getnnz(axis=1) > 0).sum())} (of {len(vids)})')

    q = sqlite3.connect(f'file:{(APPDB / "questions_genome.db").as_posix()}?mode=ro', uri=True)
    by_q = {}
    for qid, v in q.execute('SELECT q_id, verse_id FROM question_targets'):
        if v in vindex:
            by_q.setdefault(qid, set()).add(vindex[v])
    co = {}
    for vs in by_q.values():
        if len(vs) > 60:        # study-wide questions relate everything; not a pairwise signal
            continue
        for v in vs:
            co.setdefault(v, set()).update(vs - {v})

    results = {}
    for signal_name, T, truthB_matrix in (('TG', TG, TIb), ('TI', TI, TGb)):
        has_t = set(np.flatnonzero(T.getnnz(axis=1) > 0).tolist())
        pool = sorted(has_t & set(co))
        rng.shuffle(pool)
        sources = pool[:a.sources]
        for truth_name in ('A:question co-targets', 'B:other index'):
            rows = {'G': [], 'T': [], 'F': []}
            for s in sources:
                if truth_name.startswith('A'):
                    pos = co[s]
                else:
                    shared = (truthB_matrix @ truthB_matrix[s].T).toarray().ravel()
                    pos = set(np.flatnonzero(shared >= 1).tolist()) - {s}
                if len(pos) < 3:
                    continue
                g = G @ G[s]
                t = (T @ T[s].T).toarray().ravel()
                g[s] = -9
                t[s] = -9
                cg = set(np.argsort(-g)[:200].tolist())
                ct = set(np.argsort(-t)[:200].tolist()) if t.max() > 0 else set()
                cand = np.array(sorted(cg | ct))
                f = z(g[cand]) + a.weight * z(t[cand])
                ranked_f = cand[np.argsort(-f, kind='stable')].tolist()
                rows['G'].append(metrics(np.argsort(-g)[:20].tolist(), pos))
                rows['T'].append(metrics(np.argsort(-t)[:20].tolist(), pos))
                rows['F'].append(metrics(ranked_f[:20], pos))
            n = len(rows['G'])
            out = {}
            for name, rs in rows.items():
                out[name] = {k: sum(r[k] for r in rs) / n for k in ('p10', 'r20', 'ndcg')}
            ci = {k: boot([r[k] for r in rows['F']], [r[k] for r in rows['G']], rng) for k in ('p10', 'r20', 'ndcg')}
            results[f'signal={signal_name} truth={truth_name}'] = {'n': n, 'metrics': out, 'F_minus_G': ci}
            print(f'\nsignal {signal_name}, truth {truth_name}: {n} source verses')
            for name in ('G', 'T', 'F'):
                m = out[name]
                print(f'  {name}  P@10 {m["p10"]:.3f}  R@20 {m["r20"]:.3f}  nDCG@10 {m["ndcg"]:.3f}')
            print('  F-G ' + '  '.join(f'{k} {v[0]:+.3f} [{v[1]:+.3f},{v[2]:+.3f}]' for k, v in ci.items()))
    out_path = ROOT / 'local-benchmarks' / 'topic_signal_eval.json'
    out_path.write_text(json.dumps(results, indent=1), 'utf-8')
    print(f'\nwritten {out_path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
