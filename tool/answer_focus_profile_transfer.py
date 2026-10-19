"""Answer Focus profile-transfer check: does BGE-at-10 reranking help on candidate pools from profiles other than
Compass? All stage-2, wide-pool and calibration evidence to date reranks Compass's candidates only. This is a cheap,
descriptive addition to the calibration protocol's final-test stage (docs/ANSWER_FOCUS_CALIBRATION_PROTOCOL.md):
it does not select a cutoff, fit a model, or gate any decision. Reuses the frozen 10-question final-test split
(tool/answer_focus_calibration_questions.json, split == "test") and its existing grades; never imported by the app.

  python -I tool/answer_focus_profile_transfer.py run
  python -I tool/answer_focus_profile_transfer.py report

Profiles checked, chosen for distance from Compass's weights [echo, spark, thread, root] = [0.1, 0.1, 0.2, 0.6]:
  lantern [0.25, 0.15, 0.0,  0.6 ]  -- no word-level signal at all (Compass's own no-index fallback)
  gemini  [0.0,  0.0,  0.15, 0.85]  -- near-pure gene fusion, closest to a "theme match only" pool
"""
import argparse
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
import answer_focus_wide_pool as wide  # noqa: E402

OUT = ROOT / 'local-benchmarks/answer-focus-profile-transfer'
QUESTIONS = ROOT / 'tool/answer_focus_calibration_questions.json'
PROFILES = ('compass', 'lantern', 'gemini')
K = 10  # today's shipped Answer Focus depth; this checks transfer of the existing decision, not a new one


def test_questions():
    qs = [q for q in wide.read(QUESTIONS)['queries'] if q['split'] == 'test']
    assert len(qs) == 10
    return qs


def identity():
    paths = [Path(__file__), QUESTIONS, ROOT / 'engine/target/release/scripture_engine.dll',
             wide.GEN / 'answer-focus-int8-v1/model.onnx', wide.GEN / 'answer-focus-int8-v1/tokenizer.json',
             wide.GEN / 'engine-pack/manifest.json', wide.GEN / 'colbert-pack-v1/manifest.json',
             wide.GEN / 'release/content.db', wide.GEN / 'release/catalog.db',
             ROOT / 'local-benchmarks/answer-focus-calibration/queries/test']
    return {'sha256': {str(p.relative_to(ROOT)) if p.is_file() else str(p): wide.digest(p) if p.is_file() else None
                       for p in paths}, 'profiles': PROFILES, 'k': K}


def run():
    ident = identity()
    if (OUT / 'identity.json').exists():
        assert wide.read(OUT / 'identity.json') == ident, 'Input drift; do not mix runs'
    wide.write(OUT / 'identity.json', ident)
    native = wide.Native()
    try:
        for profile in PROFILES:
            for q in test_questions():
                path = OUT / 'queries' / profile / (q['id'] + '.json')
                if path.exists() and wide.read(path)['complete']:
                    print(f'cached {profile} {q["id"]}', flush=True)
                    continue
                r = native.request(op='semantic', query=q['query'], language=q['language'], profile=profile, top_k=K)
                ids = [h['verse_id'] for h in r['hits']]
                if len(ids) < K:
                    wide.write(path, {**q, 'profile': profile, 'candidates': ids, 'reranker': [], 'complete': True})
                    print(f'{profile} {q["id"]}: only {len(ids)} candidates (profile unavailable without optional pack?)')
                    continue
                corpus = wide.Corpus()
                texts = [corpus.text(v, q['language']) for v in ids]
                t = time.perf_counter()
                got = native.request(op='focus', query=q['query'], texts=texts)
                assert got['device'] == 'cpu' and len(got['scores']) == K and np.isfinite(got['scores']).all()
                wide.write(path, {**q, 'profile': profile, 'candidates': ids, 'reranker': list(got['scores']),
                                  'seconds': time.perf_counter() - t, 'complete': True})
                print(f'{profile} {q["id"]}: scored in {time.perf_counter()-t:.1f}s', flush=True)
    finally:
        native.close()


def report():
    corpus = wide.Corpus()
    grade = wide.judgments(corpus)
    qs = test_questions()
    rows = {p: [wide.read(OUT / 'queries' / p / (q['id'] + '.json')) for q in qs] for p in PROFILES}
    assert all(r['complete'] for p in PROFILES for r in rows[p]), 'Run is incomplete'
    unjudged = {}
    result = {}
    for p in PROFILES:
        per_q = []
        for r in rows[p]:
            if not r['reranker'] or r['kind'] == 'absent':
                continue
            order = sorted(range(len(r['reranker'])), key=lambda i: -r['reranker'][i])[:5]
            top5 = [r['candidates'][i] for i in order]
            grades = [grade(r['id'], v) for v in top5]
            for v, g in zip(top5, grades):
                if g is None:
                    unjudged.setdefault(p, []).append((r['id'], corpus.ref(v)))
            scored = [g for g in grades if g is not None]
            if scored:
                per_q.append({'id': r['id'], 'direct_of_judged': sum(g == 2 for g in scored),
                              'related_of_judged': sum(g >= 1 for g in scored), 'judged': len(scored)})
        result[p] = {'questions': len(per_q), 'per_question': per_q,
                     'direct_rate_judged_only': round(sum(x['direct_of_judged'] for x in per_q) /
                                                       max(1, sum(x['judged'] for x in per_q)), 4),
                     'unjudged_top5_count': len(unjudged.get(p, []))}
    out = {
        'scope': 'Descriptive transfer check on the frozen 10-question final-test split, BGE-at-10 only (no blend, '
                 'no learned combination, no cutoff). Candidates from profiles other than Compass were never part '
                 'of any prior labeled pool, so most of their top-5 is unjudged: direct_rate_judged_only is '
                 'computed only over slots with an existing grade and is NOT comparable to a fully-judged P@5. '
                 'This does not select or validate a production profile policy.',
        'k': K, 'profiles': result, 'unjudged_examples': {p: v[:10] for p, v in unjudged.items()},
    }
    wide.write(OUT / 'report.json', out)
    for p in PROFILES:
        r = result[p]
        print(f'{p:8s} questions={r["questions"]} direct_rate(judged only)={r["direct_rate_judged_only"]:.2f} '
              f'unjudged_top5_slots={r["unjudged_top5_count"]}')
    total_unjudged = sum(r['unjudged_top5_count'] for r in result.values())
    if total_unjudged:
        print(f'\n{total_unjudged} top-5 slots have no existing grade; blind-review them before citing a rate, '
              f'the same as every other stage. See report.json -> unjudged_examples.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('action', choices=('run', 'report'))
    {'run': run, 'report': report}[p.parse_args().action]()
