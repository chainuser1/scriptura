"""Does the production topic lane reproduce the judged improvement?

The human sheet judged lists made by the evaluation script; the shipped lane (tool/similar_verses.py
`similar_with_topics`, byte-for-byte what the engine returns) defines its candidates a little differently. This replays the
shipped lane on the same 60 source verses and scores its top 8 with the human judgments. A passage the reviewer never saw
counts as 0 (not related), so the number is a pessimistic lower bound.

  .venv\\Scripts\\python.exe -I tool/topic_lane_vs_judgments.py local-benchmarks/topic-judgments-from-scored-html.json
"""
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
from similar_verses import SimilarVerses  # noqa: E402

K = 8
GAIN = {0: 0.0, 1: 1.0, 2: 3.0}


def main():
    judged = json.loads(Path(sys.argv[1]).read_text('utf-8'))
    key = json.loads((ROOT / 'local-benchmarks' / 'topic-review-key.json').read_text('utf-8'))
    sv = SimilarVerses(ROOT / 'generated-artifacts' / 'engine-pack' / 'retrieval')
    rows = {'genome only (engine)': [], 'shipped topic lane': [], 'sheet fused (judged)': []}
    seen = total = 0
    for qi, q in key.items():
        marks = {v: judged.get(f'{qi}|{v}') for v in q['passages']}
        pool = sorted((GAIN[m] for m in marks.values() if m is not None), reverse=True)[:K]
        idcg = sum(g / math.log2(i + 2) for i, g in enumerate(pool))
        lists = {'genome only (engine)': [h['verse_id'] for h in sv.similar(q['source'], K)],
                 'shipped topic lane': [h['verse_id'] for h in sv.similar_with_topics(q['source'], K)],
                 'sheet fused (judged)': q['fused']}
        for name, ids in lists.items():
            js = [marks.get(v) for v in ids]
            if name == 'shipped topic lane':
                seen += sum(m is not None for m in js)
                total += len(js)
            gains = [GAIN[m] if m is not None else 0.0 for m in js]
            dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains))
            rows[name].append({'ndcg': dcg / idcg if idcg else 0.0, 'rel': sum(g > 0 for g in gains) / K})
    n = len(rows['genome only (engine)'])
    print(f'{n} sources; {seen}/{total} of the shipped lane\'s top-{K} passages had been judged ({seen / total:.0%})\n')
    for name, rs in rows.items():
        print(f'{name:24s} nDCG@{K} {sum(r["ndcg"] for r in rs) / n:.3f}   related+ {sum(r["rel"] for r in rs) / n:.3f}')
    rng = random.Random(1)
    a, b = rows['genome only (engine)'], rows['shipped topic lane']
    d = [y['ndcg'] - x['ndcg'] for x, y in zip(a, b)]
    bs = sorted(sum(d[rng.randrange(n)] for _ in d) / n for _ in range(2000))
    print(f'\nshipped lane minus genome (nDCG, unjudged = 0): {sum(d) / n:+.3f}  95% [{bs[50]:+.3f}, {bs[1949]:+.3f}]')
    return 0


if __name__ == '__main__':
    sys.exit(main())
