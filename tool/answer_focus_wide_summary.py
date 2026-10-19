"""Summarize a fully reviewed wider-pool pilot. Does not select a production policy."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import answer_focus_wide_pool as study


def main():
    rows = study.complete_rows()
    grade = study.judgments(study.Corpus())
    answerable = [r for r in rows if r['kind'] != 'absent']
    summary = []
    for depth in (*study.DEPTHS, 'full'):
        for method in ('compass', 'reranker', 'blend'):
            per = []
            totals = dict(retained=0, judged_retained=0, known_direct_before=0,
                          known_direct_discarded=0, known_nonanswers_retained=0)
            for row in answerable:
                n = len(row['candidates']) if depth == 'full' else depth
                matches = [v for v in study.variants(row) if v[0] == f'{method}@{n}']
                assert len(matches) == 1
                _, ids, scores, ranked = matches[0]
                gs = [grade(row['id'], v) for v in ranked[:5]]
                assert len(gs) == 5 and all(g is not None for g in gs), ('Unreviewed top five', row['id'], method, depth)
                f = study.filter_stats(row['id'], ids, scores, grade)
                totals['retained'] += f['retained']
                totals['judged_retained'] += f['retained_judged']
                totals['known_direct_before'] += f['known_direct_before']
                totals['known_direct_discarded'] += f['known_direct_discarded']
                totals['known_nonanswers_retained'] += f['retained_known_nonanswers']
                per.append({'id': row['id'], 'direct_p5': sum(g == 2 for g in gs)/5,
                            'related_p5': sum(g >= 1 for g in gs)/5, 'any_direct': any(g == 2 for g in gs)})
            summary.append({'depth': depth, 'method': method, 'questions': len(answerable),
                            'direct_p5': float(np.mean([r['direct_p5'] for r in per])),
                            'related_p5': float(np.mean([r['related_p5'] for r in per])),
                            'any_direct': float(np.mean([r['any_direct'] for r in per])),
                            'mean_filter_conditional_counts': totals, 'per_question': per})
    timings = [{'id': r['id'], 'pairs': len(r['candidates']),
                'seconds': sum(b['seconds'] for b in r['batches'])} for r in rows]
    absent = []
    for row in rows:
        if row['kind'] == 'absent':
            for label, ids, scores, _ in study.variants(row):
                if label.startswith('reranker@'):
                    absent.append({'id': row['id'], 'method': label,
                                   'retained': int((scores > scores.mean()).sum())})
    out = {'scope': 'Exploratory selected reused questions; eight answerable, two absent. No confirmatory intervals or production-policy selection.',
           'methods': summary, 'timings': timings, 'absent_mean_filter': absent,
           'native_top200_parity': sum(r['native_top200_exact'] for r in rows),
           'pairs_scored': sum(len(r['reranker']) for r in rows),
           'new_review_count': len(study.read(study.OUT / 'grades.json')['items']),
           'source_hashes': {str(p.relative_to(study.ROOT)): study.digest(p) for p in
                             (Path(__file__), study.OUT / 'identity.json', study.OUT / 'grades.json',
                              study.OUT / 'blind-sheet.json')}}
    study.write(study.OUT / 'summary.json', out)
    for r in summary:
        print(r['depth'], r['method'], 'direct', round(r['direct_p5'], 3), 'related', round(r['related_p5'], 3))
    print('Pairs', out['pairs_scored'], 'New judgments', out['new_review_count'])
    print('Median full-pool CPU seconds', round(float(np.median([t['seconds'] for t in timings])), 2))


if __name__ == '__main__':
    main()
