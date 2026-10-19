"""Known-positive coverage by Compass depth on the cached 36-question v2 set.

Offline diagnostic; no new inference or production changes. Not corpus-wide recall.
"""
import sys
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
from answer_focus_wide_pool import OUT, Corpus, read, write
from mathematical_retrieval_experiment import digest, norm, order, z
from volume_balance import balance, volume_of_rows


def main():
    old = ROOT / 'local-benchmarks/retrieval-v2'
    pack = ROOT / 'generated-artifacts/engine-pack'
    identity = read(old / 'encoded-identity.json')
    assert identity['engine'] == digest(pack / 'manifest.json'), 'Stale encoded queries'
    encoded = np.load(old / 'encoded.npz')
    exact = np.load(old / 'exact-colbert.npy', mmap_mode='r')
    previous = read(old / 'rankings.json')['queries']
    keys = {q['id']: q for q in read(ROOT / 'tool/search_anchors_v2.json')['queries']}
    ids = np.load(pack / 'retrieval/verse_ids.npy')
    d = np.load(pack / 'retrieval/dense_embeddings.f16.npy').astype(np.float32)
    g = norm(np.load(pack / 'retrieval/weighted_genome_embeddings.f16.npy').astype(np.float32))
    vol, corpus = volume_of_rows(ids), Corpus()
    refs = {corpus.ref(int(v)): int(v) for v in ids}
    weights = np.array(read(pack / 'manifest.json')['profiles']['compass'])
    depths = (10, 15, 20, 30, 60, 120, 200, 'full')
    results = []
    for i, q in enumerate(identity['queries']):
        assert previous[i]['id'] == q['id']
        da = balance(d @ encoded[f'd{i}'], vol, np.ones(len(ids), bool), .75)
        ga = balance(g @ encoded[f'gw{i}'], vol, np.ones(len(ids), bool), .75)
        sa = encoded[f's{i}']
        cand = np.unique(np.r_[order(da, ids, 200), order(ga, ids, 200), order(sa, ids, 200)])
        score = weights @ np.array([z(da[cand]), z(sa[cand]), z(exact[i, cand]), z(ga[cand])])
        ranked = ids[cand[order(score, ids[cand])]].tolist()
        assert ranked[:20] == previous[i]['methods']['compass'], ('Cached parity failed', q['id'])
        direct = {refs[a['reference']] for a in keys[q['id']]['anchors'] if a['grade'] == 2}
        assert direct
        found = {str(k): len(direct.intersection(ranked if k == 'full' else ranked[:k])) for k in depths}
        results.append({'id': q['id'], 'known_direct': len(direct), 'pool': len(cand), 'found': found})
    total = sum(r['known_direct'] for r in results)
    summary = {str(k): {'known_direct_found': sum(r['found'][str(k)] for r in results),
                        'micro_coverage': sum(r['found'][str(k)] for r in results)/total,
                        'macro_coverage': float(np.mean([r['found'][str(k)]/r['known_direct'] for r in results]))}
               for k in depths}
    result = {'scope': 'Previously reviewed v2 anchors; selection-biased known-positive coverage, not exhaustive recall.',
              'questions': len(results), 'known_direct_total': total, 'cached_top20_parity': len(results),
              'source_hashes': {str(p.relative_to(ROOT)): digest(p) for p in
                                (Path(__file__), old / 'encoded.npz', old / 'exact-colbert.npy',
                                 old / 'rankings.json', ROOT / 'tool/search_anchors_v2.json')},
              'summary': summary, 'per_question': results}
    write(OUT / 'candidate-coverage.json', result)
    print('Questions:', len(results), 'Known direct judgments:', total)
    for k, value in summary.items():
        print(k, value)


if __name__ == '__main__':
    with threadpool_limits(limits=4):
        main()
