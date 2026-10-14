"""Reproduce the packaged 250-question validation report with the executable reference (PLAN 12.1).

Metric definitions mirror the research validation cell (recall@10/20 = hit gold fraction, mrr@20,
weighted_ndcg@20 with target weights as gains; q_id is the unit, languages averaged within q_id).

  Phase A (cheap): encode 2,000 queries, score dense / weighted_genome / weighted_90_10 over the full corpus.
  Phase B (--colbert, ~1h CPU): stream-encode each needed candidate passage ONCE, score it against every query
  that needs it (no per-verse vector cache), then bge_dense_sparse_colbert and experiment_d.

Resumable: work files live in .artifact-staging/validation/ (gitignored). Run with the project venv:
  .venv\\Scripts\\python.exe -I tool/validate_experiment_d.py [--colbert] [--limit-qids N] [--head fp16|fp32]
"""
import argparse
import json
import math
import os
import pickle
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reference_search import (DEFAULT_EXTRACTED, SIGNAL_WEIGHTS, VOCAB, Searcher, normalize_rows,  # noqa: E402
                              top_rows, zscore)

IMPORT = DEFAULT_EXTRACTED.parent
WORK = IMPORT.parent / 'validation'
METHODS = ('dense', 'weighted_genome', 'weighted_90_10', 'bge_dense_sparse_colbert', 'experiment_d')
METRICS = ('recall@10', 'recall@20', 'mrr@20', 'weighted_ndcg@20')


def metrics(ranking, gold):
    g = set(gold)
    out = {f'recall@{k}': len(set(ranking[:k]) & g) / len(g) for k in (10, 20)}
    out['mrr@20'] = next((1.0 / r for r, v in enumerate(ranking[:20], 1) if v in g), 0.0)
    dcg = sum(gold.get(v, 0.0) / math.log2(r + 1) for r, v in enumerate(ranking[:20], 1))
    ideal = sum(w / math.log2(r + 1) for r, w in enumerate(sorted(gold.values(), reverse=True)[:20], 1))
    out['weighted_ndcg@20'] = dcg / ideal if ideal else 0.0
    return out


def atomic_pickle(obj, path):
    tmp = Path(str(path) + '.tmp')
    with open(tmp, 'wb') as f:
        pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def load_questions(report_manifest, limit):
    qids = report_manifest['question_ids'][:limit] if limit else report_manifest['question_ids']
    langs = report_manifest['languages']
    c = sqlite3.connect(f'file:{(IMPORT / "databases" / "questions_genome.db").as_posix()}?mode=ro', uri=True)
    text = {(q, lang): None for q in qids for lang in langs}
    for lang in langs:
        for q, t in c.execute(f'SELECT q_id, question FROM questions_{lang}'):
            if (q, lang) in text:
                text[(q, lang)] = t
    gold = {q: {} for q in qids}
    for q, v, w in c.execute('SELECT q_id, verse_id, weight FROM question_targets'):
        if q in gold:
            gold[q][int(v)] = float(w)
    assert all(t for t in text.values()) and all(gold.values()), 'missing question text or targets'
    return qids, langs, text, gold


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--colbert', action='store_true', help='run Phase B (ColBERT + Experiment D)')
    ap.add_argument('--limit-qids', type=int, default=0, help='smoke test on the first N q_ids (not comparable to the report)')
    ap.add_argument('--head', choices=('fp16', 'fp32'), default='fp16', help='report used the FP16 head')
    a = ap.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)

    ext = DEFAULT_EXTRACTED
    report = json.loads((ext / 'scripture-genome-question-hidden4096-full' / 'validation_q250.json').read_text('utf-8'))
    qids, langs, text, gold = load_questions(report['manifest'], a.limit_qids)
    keys = [(q, lang) for q in qids for lang in langs]
    print(f'{len(qids)} q_ids x {len(langs)} languages = {len(keys)} rows', flush=True)

    s = Searcher(ext)
    if a.head == 'fp16':
        with np.load(ext / 'scripture-genome-question-hidden4096-optimized' / 'head_fp16.npz', allow_pickle=False) as z:
            s.head = {'0.weight': z['w0'].astype(np.float32), '0.bias': z['b0'].astype(np.float32),
                      '2.weight': z['w1'].astype(np.float32), '2.bias': z['b1'].astype(np.float32)}
    stored_w = np.load(ext / 'scripture-retrieval-english-v1' / 'weighted_genome_embeddings.f16.npy', allow_pickle=False)
    wg = normalize_rows(stored_w.astype(np.float32))  # the research cell used the stored weighted vectors
    vids = s.verse_ids

    # ---- Phase A: encode queries (cached) --------------------------------------------------------
    qpath = WORK / f'queries-{len(keys)}.pkl'
    if qpath.exists():
        enc = pickle.load(open(qpath, 'rb'))
        assert enc['keys'] == keys
        enc = enc['enc']
    else:
        t0 = time.perf_counter()
        enc = s.encoder.encode([text[k] for k in keys], batch=16)
        atomic_pickle({'keys': keys, 'enc': enc}, qpath)
        print(f'encoded {len(keys)} queries in {time.perf_counter() - t0:.0f}s', flush=True)

    rows = []
    for qi, (q, lang) in enumerate(keys):
        d, w, c = enc[qi]
        g = s.genome_of(d)
        gw = normalize_rows((g * s.sw)[None, :])[0]
        sv = np.zeros(VOCAB, dtype=np.float32)
        for t, x in w.items():
            sv[t] = x
        dense_all = (s.dense @ d).astype(np.float64)
        genome_all = (wg @ gw).astype(np.float64)
        sparse_all = (s.csr @ sv).astype(np.float64)
        mix_all = 0.90 * zscore(genome_all) + 0.10 * zscore(dense_all)
        cand = np.unique(np.concatenate([top_rows(x, vids, 200) for x in (dense_all, sparse_all, genome_all)]))
        rank = lambda sc, ids=vids: [int(ids[i]) for i in top_rows(sc, ids, 20)]  # noqa: E731
        rows.append({
            'cand': cand, 'dense': dense_all[cand], 'sparse': sparse_all[cand], 'genome': genome_all[cand],
            'm': {'dense': metrics(rank(dense_all), gold[q]), 'weighted_genome': metrics(rank(genome_all), gold[q]),
                  'weighted_90_10': metrics(rank(mix_all), gold[q])},
            'cand_gold_recall': len(set(vids[cand].tolist()) & set(gold[q])) / len(gold[q]),
        })
    print('phase A scored', flush=True)

    # ---- Phase B: ColBERT, streamed per passage ---------------------------------------------------
    if a.colbert:
        cpath = WORK / f'colbert-{len(keys)}-{a.head}.pkl'
        col = [np.full(len(r['cand']), np.nan) for r in rows]
        done = np.zeros(len(vids), dtype=bool)
        if cpath.exists():
            col, done = pickle.load(open(cpath, 'rb'))
            print(f'resumed: {int(done.sum())} passages done', flush=True)
        need = {}
        for qi, r in enumerate(rows):
            for v in r['cand']:
                need.setdefault(int(v), []).append(qi)
        todo = [v for v in need if not done[v]]
        lens = np.array([len(x) for x in s.encoder.tok([s.texts[v] for v in todo])['input_ids']])
        todo = [todo[i] for i in np.argsort(lens, kind='stable')]
        print(f'{len(need)} unique candidate passages, {len(todo)} to encode, '
              f'{sum(len(x) for x in need.values())} (query,passage) pairs', flush=True)
        qcat = {qi: enc[qi][2] for qi in range(len(rows))}
        t0, last_ckpt, n_done = time.perf_counter(), time.perf_counter(), 0
        for s0 in range(0, len(todo), 64):
            chunk = todo[s0:s0 + 64]
            vecs = s.encoder.encode([s.texts[v] for v in chunk], batch=16)
            for v, (_, _, p) in zip(chunk, vecs):
                qs = need[v]
                big = np.concatenate([qcat[qi] for qi in qs], axis=0)
                mx = (big @ p.T).max(axis=1)
                offs = np.cumsum([0] + [len(qcat[qi]) for qi in qs])
                sums = np.add.reduceat(mx, offs[:-1])
                for qi, ssum, ln in zip(qs, sums, np.diff(offs)):
                    col[qi][np.searchsorted(rows[qi]['cand'], v)] = ssum / ln
                done[v] = True
            n_done += len(chunk)
            if time.perf_counter() - last_ckpt > 300 or s0 + 64 >= len(todo):
                atomic_pickle((col, done), cpath)
                last_ckpt = time.perf_counter()
                el = time.perf_counter() - t0
                print(f'  {n_done}/{len(todo)} passages  {el / 60:.1f} min  ETA {(len(todo) - n_done) * el / n_done / 60:.1f} min',
                      flush=True)
        assert not any(np.isnan(c).any() for c in col)
        for qi, (q, lang) in enumerate(keys):
            r = rows[qi]
            zc = zscore(col[qi])
            zd, zs, zg = zscore(r['dense']), zscore(r['sparse']), zscore(r['genome'])
            cv = vids[r['cand']]
            three = 0.40 * zd + 0.20 * zs + 0.40 * zc
            exp_d = (SIGNAL_WEIGHTS['dense'] * zd + SIGNAL_WEIGHTS['sparse'] * zs
                     + SIGNAL_WEIGHTS['colbert'] * zc + SIGNAL_WEIGHTS['genome'] * zg)
            r['m']['bge_dense_sparse_colbert'] = metrics([int(cv[i]) for i in top_rows(three, cv, 20)], gold[q])
            r['m']['experiment_d'] = metrics([int(cv[i]) for i in top_rows(exp_d, cv, 20)], gold[q])

    # ---- compare with the packaged report ---------------------------------------------------------
    have = [m for m in METHODS if m in rows[0]['m']]
    ref_all, ref_lang = report['overall_cluster_bootstrap'], report['by_language']
    print(f'\nmethod / metric                         mine    report  [95% interval]     delta   in-interval')
    summary = {}
    for m in have:
        for met in METRICS:
            per_q = [np.mean([rows[keys.index((q, lang))]['m'][m][met] for lang in langs]) for q in qids]
            mean = float(np.mean(per_q))
            ref = ref_all[m][met]
            ok = ref['low'] <= mean <= ref['high']
            summary[f'{m}/{met}'] = {'mine': mean, 'report': ref['mean'], 'low': ref['low'], 'high': ref['high']}
            print(f"{m:26s} {met:18s} {mean:7.4f}  {ref['mean']:7.4f}  [{ref['low']:.4f},{ref['high']:.4f}]  "
                  f"{mean - ref['mean']:+.4f}  {'yes' if ok else 'NO'}")
    cand = float(np.mean([np.mean([rows[keys.index((q, lang))]['cand_gold_recall'] for lang in langs]) for q in qids]))
    print(f"candidate-union gold recall   mine {cand:.4f}  report {report['candidate_union_recall']['mean']:.4f}")
    if have:
        print('\nby language, english:', {m: {k: round(float(np.mean([rows[keys.index((q, "english"))]['m'][m][k] for q in qids])), 4)
                                            for k in METRICS} for m in have if 'english' in langs})
        print('report  english:', {m: {k: round(ref_lang['english'][m][k], 4) for k in METRICS} for m in have})
    (WORK / f'summary-{len(keys)}-{a.head}{"-colbert" if a.colbert else ""}.json').write_text(
        json.dumps({'head': a.head, 'rows': len(keys), 'summary': summary, 'candidate_gold_recall': cand}, indent=2), 'utf-8')


if __name__ == '__main__':
    main()
