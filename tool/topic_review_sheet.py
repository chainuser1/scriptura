"""Human-judged check of the topic signal (the step the proxy evaluation cannot replace).

  .venv\\Scripts\\python.exe -I tool/topic_review_sheet.py             # writes local-benchmarks/topic-review.html (+ key)
  .venv\\Scripts\\python.exe -I tool/topic_review_sheet.py --score F    # F = the exported judgments JSON

For N source verses (spread over the whole canon) the sheet pools the top K neighbours of the genome-only ranking and of
the fused ranking (genome + 0.5 x topic overlap), removes duplicates and shuffles them; the reviewer sees only passages,
never which method returned them, and marks 0 = unrelated, 1 = related, 2 = clearly the same theme. Scoring compares the
two methods with a paired bootstrap on nDCG@K and precision of "related or better".

The sheet contains scripture text, so it stays in local-benchmarks/ (gitignored).
"""
import argparse
import bisect
import html
import json
import math
import random
import sqlite3
import sys
from pathlib import Path

import numpy as np
import scipy.sparse as sp

ROOT = Path(__file__).resolve().parent.parent
GEN = ROOT / 'generated-artifacts'
OUT = ROOT / 'local-benchmarks'
BACKUP = ROOT.parent / 'scriptura' / 'app-backups' / 'scriptures_reader_mobile-before-phase0-20261011' / 'assets' / 'resources' / 'db'
WEIGHT, K = 0.5, 8
GAIN = {0: 0.0, 1: 1.0, 2: 3.0}


def z(x):
    s = x.std()
    return (x - x.mean()) / s if s > 0 else x * 0


def load_topics(vindex):
    c = sqlite3.connect(f'file:{(BACKUP / "topical-guide.db").as_posix()}?mode=ro&immutable=1', uri=True)
    topics, rows, cols = {}, [], []
    for slug, v in c.execute('SELECT topic_slug, verse_id FROM topic_verse_index'):
        if v in vindex:
            rows.append(vindex[v])
            cols.append(topics.setdefault(slug, len(topics)))
    m = sp.csr_matrix((np.ones(len(rows), dtype=np.float32), (rows, cols)), shape=(len(vindex), len(topics)))
    m.data[:] = 1.0
    df = np.asarray(m.sum(axis=0)).ravel()
    w = m.multiply(np.log((m.shape[0] + 1) / (df + 1)) + 1).tocsr()
    norm = np.sqrt(np.asarray(w.multiply(w).sum(axis=1)).ravel()).clip(1e-9)
    return sp.diags(1 / norm) @ w


def make(n_sources, seed):
    rng = random.Random(seed)
    ret = GEN / 'engine-pack' / 'retrieval'
    vids = np.load(ret / 'verse_ids.npy')
    G = np.load(ret / 'weighted_genome_embeddings.f16.npy').astype(np.float32)
    vindex = {int(v): i for i, v in enumerate(vids)}
    T = load_topics(vindex)
    covered = np.flatnonzero(T.getnnz(axis=1) >= 3).tolist()
    # spread over the canon: one bucket per slice of the verse-id range
    covered.sort()
    per = n_sources
    sources = []
    step = len(covered) / per
    for i in range(per):
        lo, hi = int(i * step), int((i + 1) * step)
        sources.append(covered[rng.randrange(lo, max(hi, lo + 1))])

    content = sqlite3.connect(f'file:{(GEN / "release" / "content.db").as_posix()}?mode=ro', uri=True)
    cat = sqlite3.connect(f'file:{(GEN / "release" / "catalog.db").as_posix()}?mode=ro', uri=True)
    chapters = cat.execute('SELECT book_id, chapter, first_verse_id FROM chapters ORDER BY first_verse_id').fetchall()
    firsts = [c[2] for c in chapters]
    names = dict(cat.execute('SELECT book_id, name FROM book_names_english'))

    def ref(v):
        b, ch, lo = chapters[bisect.bisect_right(firsts, v) - 1]
        return f'{names[b]} {ch}:{v - lo + 1}'

    def text(v):
        return content.execute('SELECT text FROM text_english WHERE verse_id = ?', (v,)).fetchone()[0]

    key, sections = {}, []
    for qi, s in enumerate(sources):
        g = G @ G[s]
        t = (T @ T[s].T).toarray().ravel()
        g[s] = t[s] = -9
        cg = np.argsort(-g)[:200]
        ct = np.argsort(-t)[:200] if t.max() > 0 else np.array([], dtype=int)
        cand = np.array(sorted(set(cg.tolist()) | set(ct.tolist())))
        f = z(g[cand]) + WEIGHT * z(t[cand])
        fused = cand[np.argsort(-f, kind='stable')][:K].tolist()
        base = np.argsort(-g)[:K].tolist()
        pool = sorted(set(base) | set(fused))
        rng.shuffle(pool)
        key[str(qi)] = {'source': int(vids[s]), 'base': [int(vids[r]) for r in base], 'fused': [int(vids[r]) for r in fused],
                        'passages': [int(vids[r]) for r in pool]}
        sections.append((qi, int(vids[s]), [int(vids[r]) for r in pool]))

    parts = ['<!doctype html><meta charset="utf-8"><title>Similar verses review</title>'
             '<style>body{font:16px/1.5 system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem}'
             'h2{margin-top:2.5rem;border-bottom:2px solid #d3167b}.src{background:#f9fafb;padding:.6rem;border-left:4px solid #0e183e}'
             '.p{padding:.5rem 0;border-bottom:1px dotted #ccc}.r{font-weight:600}label{margin-right:1rem}'
             '#bar{position:sticky;top:0;background:#fff;padding:.5rem 0;border-bottom:2px solid #0e183e}</style>'
             '<div id="bar"><b>Similar verses</b> &middot; <span id="done">0</span> judged &middot; '
             '<button onclick="save()">Download judgments (JSON)</button> '
             '<small>For each passage: how related is it to the SOURCE verse? 0 = unrelated, 1 = related, 2 = clearly the same theme.'
             ' Progress is saved in this browser.</small></div>']
    for qi, sv, pool in sections:
        parts.append(f'<h2>{qi + 1}.</h2><div class="src"><b>Source: {html.escape(ref(sv))}</b><br>{html.escape(text(sv))}</div>')
        for v in pool:
            parts.append(f'<div class="p"><div class="r">{html.escape(ref(v))}</div><div>{html.escape(text(v))}</div><div>'
                         + ''.join(f'<label><input type="radio" name="q{qi}_{v}" value="{sc}" onchange="mark(\'{qi}\',\'{v}\',{sc})"> {sc}</label>'
                                   for sc in (0, 1, 2)) + '</div></div>')
    parts.append("""<script>
const J=JSON.parse(localStorage.getItem('topicreview')||'{}');
function mark(q,v,s){J[q+'|'+v]=s;localStorage.setItem('topicreview',JSON.stringify(J));count();}
function count(){document.getElementById('done').textContent=Object.keys(J).length;}
for(const k in J){const [q,v]=k.split('|');const el=document.querySelector(`input[name="q${q}_${v}"][value="${J[k]}"]`);if(el)el.checked=true;}
count();
function save(){const b=new Blob([JSON.stringify(J,null,1)],{type:'application/json'});const a=document.createElement('a');
a.href=URL.createObjectURL(b);a.download='topic-judgments.json';a.click();}
</script>""")
    OUT.mkdir(exist_ok=True)
    (OUT / 'topic-review.html').write_text('\n'.join(parts), 'utf-8')
    (OUT / 'topic-review-key.json').write_text(json.dumps(key), 'utf-8')
    total = sum(len(p) for _, _, p in sections)
    print(f'{len(sources)} source verses, {total} passages to judge -> {OUT / "topic-review.html"}')


def score(path):
    judged = json.loads(Path(path).read_text('utf-8'))
    key = json.loads((OUT / 'topic-review-key.json').read_text('utf-8'))
    per = {'genome only': [], 'genome + topics': []}
    for qi, q in key.items():
        marks = {v: judged.get(f'{qi}|{v}') for v in q['passages']}
        if not all(m is not None for m in marks.values()):
            continue  # score only fully judged sources
        pool = sorted((GAIN[m] for m in marks.values()), reverse=True)[:K]
        idcg = sum(g / math.log2(i + 2) for i, g in enumerate(pool))
        for name, ids in (('genome only', q['base']), ('genome + topics', q['fused'])):
            js = [marks[v] for v in ids]
            dcg = sum(GAIN[m] / math.log2(i + 2) for i, m in enumerate(js))
            per[name].append({'ndcg': dcg / idcg if idcg else 0.0, 'prec': sum(m >= 1 for m in js) / len(js),
                              'clear': sum(m == 2 for m in js) / len(js)})
    n = len(per['genome only'])
    if n == 0:
        sys.exit('no fully judged source verses found')
    print(f'{n} fully judged source verses\n')
    for name, rows in per.items():
        print(f'{name:18s} nDCG@{K} {sum(r["ndcg"] for r in rows) / n:.3f}  related+ {sum(r["prec"] for r in rows) / n:.3f}  '
              f'clearly same theme {sum(r["clear"] for r in rows) / n:.3f}')
    rng = random.Random(1)
    for k in ('ndcg', 'prec', 'clear'):
        d = [b[k] - a[k] for a, b in zip(per['genome only'], per['genome + topics'])]
        bs = sorted(sum(d[rng.randrange(n)] for _ in d) / n for _ in range(2000))
        print(f'  topics minus genome, {k:5s}: {sum(d) / n:+.3f}  95% [{bs[50]:+.3f}, {bs[1949]:+.3f}]')
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--score', help='exported judgments JSON')
    ap.add_argument('--sources', type=int, default=60)
    ap.add_argument('--seed', type=int, default=21)
    a = ap.parse_args()
    return score(a.score) if a.score else (make(a.sources, a.seed) or 0)


if __name__ == '__main__':
    sys.exit(main())
