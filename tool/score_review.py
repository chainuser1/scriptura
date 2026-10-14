"""Score the search profiles from a completed review (review-judgments.json + review-key.json).

Per profile: mean nDCG@10 (gain 0/1/3 for judgments 0/1/2), precision@10 of "related or better", MRR of the first
"directly answers", and the share of queries with at least one direct answer in the top 10; each with a paired
bootstrap interval against the default profile (compass). Unjudged passages count as not relevant.

  .venv\\Scripts\\python.exe -I tool/score_review.py [judgments.json]
"""
import json
import math
import random
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / 'local-benchmarks'
GAIN = {0: 0.0, 1: 1.0, 2: 3.0}


def ndcg(gains):
    dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains))
    ideal = sorted(gains, reverse=True)
    idcg = sum(g / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def main():
    jpath = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT / 'review-judgments.json'
    key = json.loads((OUT / 'review-key.json').read_text('utf-8'))
    judged = json.loads(jpath.read_text('utf-8'))
    profiles, top = key['profiles'], key['top']
    per = {p: [] for p in profiles}
    covered = 0
    for qi, q in key['queries'].items():
        marks = {v: judged.get(f'{qi}|{v}') for v in q['passages']}
        if not any(m is not None for m in marks.values()):
            continue  # query not reviewed
        covered += 1
        for p in profiles:
            ranked = sorted((r[p], v) for v, r in q['passages'].items() if p in r)[:top]
            j = [marks[v] if marks[v] is not None else 0 for _, v in ranked]
            # normalise against everything judged for that query, so nDCG is comparable across profiles
            pool = sorted((GAIN[m] for m in marks.values() if m is not None), reverse=True)[:top]
            dcg = sum(GAIN[m] / math.log2(i + 2) for i, m in enumerate(j))
            idcg = sum(g / math.log2(i + 2) for i, g in enumerate(pool))
            first = next((i for i, m in enumerate(j) if m == 2), None)
            per[p].append({'ndcg': dcg / idcg if idcg else 0.0, 'prec': sum(m >= 1 for m in j) / top,
                           'mrr': 0.0 if first is None else 1.0 / (first + 1), 'hit': float(first is not None)})
    if covered == 0:
        sys.exit('no reviewed queries found in the judgments file')
    print(f'{covered} reviewed queries')
    print()
    base = per.get('compass') or next(iter(per.values()))
    rng = random.Random(1)
    print(f'{"profile":10s}{"nDCG@10":>9s}{"P@10":>8s}{"MRR":>7s}{"has answer":>12s}   vs compass (nDCG, 95% interval)')
    for p, rows in per.items():
        m = lambda k: sum(r[k] for r in rows) / len(rows)  # noqa: E731
        diffs = [rows[i]['ndcg'] - base[i]['ndcg'] for i in range(len(rows))]
        boots = sorted(sum(diffs[rng.randrange(len(diffs))] for _ in diffs) / len(diffs) for _ in range(2000))
        ci = f'{sum(diffs) / len(diffs):+.3f} [{boots[50]:+.3f}, {boots[1949]:+.3f}]' if p != 'compass' else '-'
        print(f'{p:10s}{m("ndcg"):9.3f}{m("prec"):8.3f}{m("mrr"):7.3f}{m("hit"):12.3f}   {ci}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
