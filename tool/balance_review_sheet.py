"""Blind A/B review of volume balance (docs/superpowers/plans/2026-10-14-volume-balance.md, Task 5).

  .venv\\Scripts\\python.exe -I tool/balance_review_sheet.py similar            # local-benchmarks/balance-review-similar.html
  .venv\\Scripts\\python.exe -I tool/balance_review_sheet.py search             # local-benchmarks/balance-review-search.html
  .venv\\Scripts\\python.exe -I tool/balance_review_sheet.py --score FILE       # FILE = the downloaded judgments JSON

For every item you see a source (a verse, or a question) and two lists, A and B. One list is the app without volume balance,
the other with it. Which is which is shuffled and saved only in the key file. For each item mark "A is better", "B is better"
or "about the same". Only items whose two lists differ are shown.

Decision rule, fixed before judging (judging is optional): volume balance stays on unless the balanced list wins less than
45% of the decided pairs (ties left out).
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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
OUT = ROOT / 'local-benchmarks'
GEN = ROOT / 'generated-artifacts'
VOLUME_NAMES = ['Old Testament', 'New Testament', 'Book of Mormon', 'Doctrine and Covenants', 'Pearl of Great Price']
SEED = 20261014
LIST_LEN = 8


class Text:
    """Verse text and references from the shipped content and catalog databases."""

    def __init__(self):
        self.content = sqlite3.connect(f'file:{(GEN / "release" / "content.db").as_posix()}?mode=ro', uri=True)
        cat = sqlite3.connect(f'file:{(GEN / "release" / "catalog.db").as_posix()}?mode=ro', uri=True)
        self.chapters = cat.execute('SELECT book_id, chapter, first_verse_id FROM chapters ORDER BY first_verse_id').fetchall()
        self.firsts = [c[2] for c in self.chapters]
        self.names = dict(cat.execute('SELECT book_id, name FROM book_names_english'))

    def ref(self, v):
        b, ch, lo = self.chapters[bisect.bisect_right(self.firsts, v) - 1]
        return f'{self.names[b]} {ch}:{v - lo + 1}'

    def text(self, v):
        return self.content.execute('SELECT text FROM text_english WHERE verse_id = ?', (v,)).fetchone()[0]


def page(title, intro, items_html, storage_key, download_name):
    return f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
body{{font:16px/1.5 system-ui,Segoe UI,Roboto,sans-serif;max-width:1100px;margin:0 auto;padding:0 1rem 4rem;color:#0e183e}}
#bar{{position:sticky;top:0;background:#fff;padding:.6rem 0;border-bottom:2px solid #0e183e;z-index:2}}
h1{{font-size:1.3rem;margin:.6rem 0}} .intro{{background:#f3f4f8;padding:.8rem 1rem;border-radius:8px}}
.item{{margin:2rem 0;border-top:3px solid #d3167b;padding-top:.6rem}}
.src{{background:#fff7fb;border-left:4px solid #d3167b;padding:.5rem .8rem;margin:.5rem 0}}
.scope{{display:inline-block;background:#0e183e;color:#fff;border-radius:999px;padding:.05rem .7rem;font-size:.85rem}}
.cols{{display:grid;grid-template-columns:1fr 1fr;gap:1rem}} @media(max-width:800px){{.cols{{grid-template-columns:1fr}}}}
.col{{border:1px solid #c9cde0;border-radius:8px;padding:.4rem .8rem}} .col h3{{margin:.2rem 0}}
.v{{padding:.35rem 0;border-bottom:1px dotted #ccc}} .r{{font-weight:600}} .t{{font-size:.95rem}}
.pick label{{margin-right:1.2rem;font-weight:600}} .pick{{margin:.6rem 0}}
button{{font:inherit;padding:.3rem .8rem}}
</style>
<div id="bar"><b>{html.escape(title)}</b> &middot; <span id="done">0</span> of <span id="total">0</span> judged &middot;
<button onclick="save()">Download judgments (JSON)</button></div>
<div class="intro">{intro}</div>
{items_html}
<script>
const KEY='{storage_key}';const J=JSON.parse(localStorage.getItem(KEY)||'{{}}');
function mark(id,v){{J[id]=v;localStorage.setItem(KEY,JSON.stringify(J));count();}}
function count(){{document.getElementById('done').textContent=Object.keys(J).length;
 document.getElementById('total').textContent=document.querySelectorAll('.item').length;}}
for(const id in J){{const el=document.querySelector(`input[name="${{id}}"][value="${{J[id]}}"]`);if(el)el.checked=true;}}
count();
function save(){{const b=new Blob([JSON.stringify(J,null,1)],{{type:'application/json'}});const a=document.createElement('a');
a.href=URL.createObjectURL(b);a.download='{download_name}';a.click();}}
</script>"""


def list_html(label, verses, text):
    rows = ''.join(f'<div class="v"><div class="r">{html.escape(text.ref(v))}</div><div class="t">{html.escape(text.text(v))}</div></div>' for v in verses)
    return f'<div class="col"><h3>{label}</h3>{rows}</div>'


def item_html(i, source_html, scope, a, b, text):
    return (f'<div class="item" id="{i}"><span class="scope">{html.escape(scope)}</span>'
            f'<div class="src">{source_html}</div>'
            f'<div class="cols">{list_html("List A", a, text)}{list_html("List B", b, text)}</div>'
            f'<div class="pick"><label><input type="radio" name="{i}" value="A" onchange="mark(\'{i}\',\'A\')"> A is better</label>'
            f'<label><input type="radio" name="{i}" value="B" onchange="mark(\'{i}\',\'B\')"> B is better</label>'
            f'<label><input type="radio" name="{i}" value="same" onchange="mark(\'{i}\',\'same\')"> about the same</label></div></div>')


# ---- similar verses (the Python reference; no engine needed) ---------------------------------------------------------
def make_similar():
    import numpy as np
    from similar_verses import SimilarVerses, TOPICS_DB
    from volume_balance import STRENGTH, volume_ranges

    sv = SimilarVerses()
    text = Text()
    rng = random.Random(SEED)
    ids = sv.verse_ids
    by_verse = sv._topics(TOPICS_DB)[0]
    vr = [(v['first'], v['last']) for v in volume_ranges()]
    mixes = [(0, 1), (0, 2), (1, 2), (2, 3)]   # Bible, OT + BoM, NT + BoM, BoM + D&C
    plan = [('Across the canon', None, None)] * 20 + [
        (f'{VOLUME_NAMES[x]} + {VOLUME_NAMES[y]}', [vr[x], vr[y]], (x, y)) for x, y in mixes for _ in range(5)]
    pool = [int(x) for x in ids if by_verse.get(int(x))]
    rng.shuffle(pool)
    items, key, skipped, used, n = [], {}, 0, set(), 0
    for scope, flt, mix in plan:
        for src in pool:
            if src in used or (mix and not any(lo <= src <= hi for lo, hi in flt)):
                continue
            allowed = None
            if flt:
                m = np.zeros(len(ids), dtype=bool)
                for lo, hi in flt:
                    m |= (ids >= lo) & (ids <= hi)
                allowed = ids[m]
            off = [h['verse_id'] for h in sv.similar_with_topics(src, LIST_LEN, allowed, TOPICS_DB)]
            on = [h['verse_id'] for h in sv.similar_with_topics(src, LIST_LEN, allowed, TOPICS_DB, volume_balance=STRENGTH)]
            if off == on:
                skipped += 1
                continue
            used.add(src)
            n += 1
            iid = f'S{n:02d}'
            a_is_off = rng.random() < 0.5
            a, b = (off, on) if a_is_off else (on, off)
            src_html = f'<b>{html.escape(text.ref(src))}</b><br>{html.escape(text.text(src))}'
            items.append((rng.random(), item_html(iid, src_html, scope, a, b, text)))
            key[iid] = {'scope': 'canon' if flt is None else 'mix', 'source': src, 'A': 'off' if a_is_off else 'on'}
            break
    items.sort()
    intro = ('<b>Which list is the better answer to "verses like this one"?</b> The source verse is shown first. Judge the meaning: '
             'do the verses speak to the same thing, not only sound alike or sit in the same book. One list is the app today and '
             'one gives other volumes a fairer chance; you are not told which. The grey label says which volumes were searched.')
    OUT.mkdir(exist_ok=True)
    (OUT / 'balance-review-similar.html').write_text(
        page('Balance review: similar verses', intro, ''.join(h for _, h in items), 'balance-similar', 'balance-judgments-similar.json'), 'utf-8')
    (OUT / 'balance-review-similar-key.json').write_text(json.dumps(key, indent=1), 'utf-8')
    print(f'{len(items)} items ({skipped} candidates skipped because both lists were identical) -> {OUT / "balance-review-similar.html"}')


def make_search():
    import ctypes
    from review_sheet import Engine as BaseEngine, load_queries
    from volume_balance import STRENGTH

    class Engine(BaseEngine):
        def call(self, body):
            p = self.lib.se_request(self.h, json.dumps(body).encode())
            out = json.loads(ctypes.string_at(p).decode())
            self.lib.se_free_string(p)
            if 'error' in out:
                raise RuntimeError(out['error'])
            return [h['verse_id'] for h in out['hits']]

    eng = Engine()
    text = Text()
    rng = random.Random(SEED + 1)
    items, key, skipped, n = [], {}, 0, 0
    for q in load_queries(400, rng):
        if n == 40:
            break
        req = {'op': 'semantic', 'query': q, 'top_k': LIST_LEN, 'profile': 'compass'}
        off, on = eng.call({**req, 'volume_balance': 0.0}), eng.call({**req, 'volume_balance': STRENGTH})
        if off == on:
            skipped += 1
            continue
        n += 1
        iid = f'Q{n:02d}'
        a_is_off = rng.random() < 0.5
        a, b = (off, on) if a_is_off else (on, off)
        items.append((rng.random(), item_html(iid, f'<b>Question:</b> {html.escape(q)}', 'Across the canon', a, b, text)))
        key[iid] = {'scope': 'canon', 'query': q, 'A': 'off' if a_is_off else 'on'}
    items.sort()
    intro = ('<b>Which list better answers the question?</b> Judge the meaning: which verses actually speak to what is asked. '
             'One list is the app today and one gives other volumes a fairer chance; you are not told which.')
    OUT.mkdir(exist_ok=True)
    (OUT / 'balance-review-search.html').write_text(
        page('Balance review: meaning search', intro, ''.join(h for _, h in items), 'balance-search', 'balance-judgments-search.json'), 'utf-8')
    (OUT / 'balance-review-search-key.json').write_text(json.dumps(key, indent=1), 'utf-8')
    print(f'{len(items)} items ({skipped} candidates skipped because both lists were identical) -> {OUT / "balance-review-search.html"}')


def wilson(wins, n, z=1.96):
    if n == 0:
        return 0.0, 0.0, 0.0
    p = wins / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, c - h, c + h


def score(path):
    j = json.loads(Path(path).read_text('utf-8'))
    kind = 'similar' if next(iter(j), 'S').startswith('S') else 'search'   # item ids are S01.. or Q01..
    key = json.loads((OUT / f'balance-review-{kind}-key.json').read_text('utf-8'))
    groups = {}
    for iid, mark in j.items():
        k = key.get(iid)
        if k is None:
            continue
        other = 'off' if k['A'] == 'on' else 'on'
        winner = 'tie' if mark == 'same' else (k['A'] if mark == 'A' else other)
        label = {'canon': 'Across the canon', 'mix': 'Two volumes'}[k['scope']]
        for g in ('All', label):
            groups.setdefault(g, {'on': 0, 'off': 0, 'tie': 0})[winner] += 1
    print(f'judged {len(j)} of {len(key)} items')
    for g in sorted(groups):
        c = groups[g]
        decided = c['on'] + c['off']
        p, lo, hi = wilson(c['on'], decided)
        verdict = ('KEEP ON' if not decided or p >= 0.45 else 'SWITCH OFF') if g == 'All' else ''
        print(f'  {g:20s} balanced wins {c["on"]:2d}, today wins {c["off"]:2d}, same {c["tie"]:2d}  '
              f'share {p:.0%} [{lo:.0%}, {hi:.0%}] {verdict}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('kind', nargs='?', choices=['similar', 'search'])
    ap.add_argument('--score')
    a = ap.parse_args()
    if a.score:
        return score(a.score)
    if a.kind == 'similar':
        return make_similar()
    return make_search()


if __name__ == '__main__':
    main()
