"""Human check of trails: 'does this verse belong on this trail?'

  .venv\\Scripts\\python.exe -I tool/trail_review_sheet.py              # writes local-benchmarks/trail-review.html (+ key)
  .venv\\Scripts\\python.exe -I tool/trail_review_sheet.py --score F     # F = the exported judgments JSON

Each starter trail (and two verse-seeded trails) is played 12 cards by the real engine with a scripted feedback pattern
(like, skip, like, dislike, repeated), so the sheet shows what a reader would actually be given. 0 = no, 1 = related, 2 = yes.
"""
import argparse
import bisect
import ctypes
import html
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from review_sheet import Engine as BaseEngine, GEN, OUT, ROOT  # noqa: E402

PATTERN = ['like', 'skip', 'like', 'dislike']
CARDS = 12


class Engine(BaseEngine):
    def call(self, body):
        p = self.lib.se_request(self.h, json.dumps(body).encode())
        out = json.loads(ctypes.string_at(p).decode())
        self.lib.se_free_string(p)
        if 'error' in out:
            raise RuntimeError(out['error'])
        return out


def play(eng, seed, moods):
    events, history, verses = [], [], []
    for i in range(CARDS):
        r = eng.call({'op': 'trail_next', 'k': 5, 'step': len(history), 'seed': seed, 'events': events, 'recent': history[-5:],
                      'moods': moods, 'mood_strength': 0.5, 'focus': 0.5, 'filter': None, 'language': 'english'})
        if not r['hits']:
            break
        v = r['hits'][0]['verse_id']
        verses.append(v)
        history.append(v)
        events.append({'verse_id': v, 'action': 'shown'})
        events.append({'verse_id': v, 'action': PATTERN[i % len(PATTERN)]})
    return verses


def make():
    starters = json.loads((ROOT / 'assets' / 'trail_starters.json').read_text('utf-8'))['starters']
    moods = {m['id']: m for m in json.loads((ROOT / 'assets' / 'trail_moods.json').read_text('utf-8'))['moods']}
    eng = Engine()
    content = sqlite3.connect(f'file:{(GEN / "release" / "content.db").as_posix()}?mode=ro', uri=True)
    cat = sqlite3.connect(f'file:{(GEN / "release" / "catalog.db").as_posix()}?mode=ro', uri=True)
    chapters = cat.execute('SELECT book_id, chapter, first_verse_id FROM chapters ORDER BY first_verse_id').fetchall()
    firsts = [c[2] for c in chapters]
    names = dict(cat.execute('SELECT book_id, name FROM book_names_english'))

    def ref(v):
        b, ch, lo = chapters[bisect.bisect_right(firsts, v) - 1]
        return f'{names[b]} {ch}:{v - lo + 1}'

    trails = [(s['title'], s['mood'], {'text': s['question']}, [moods[s['mood']]['genes']]) for s in starters]
    trails += [('John 3:16 (no mood)', '', {'verse_id': 26137}, []), ('Alma 32:21 (no mood)', '', {'verse_id': 34000}, [])]
    key, parts = {}, ['<!doctype html><meta charset="utf-8"><title>Trail review</title><style>body{font:16px/1.5 system-ui;max-width:860px;'
                      'margin:2rem auto;padding:0 1rem}h2{margin-top:2.5rem;border-bottom:2px solid #d3167b}.p{padding:.5rem 0;'
                      'border-bottom:1px dotted #ccc}.r{font-weight:600}label{margin-right:1rem}#bar{position:sticky;top:0;background:#fff;'
                      'padding:.5rem 0;border-bottom:2px solid #0e183e}</style><div id="bar"><b>Trail review</b> &middot; <span id="done">0'
                      '</span> judged &middot; <button onclick="save()">Download judgments (JSON)</button> <small>Does this verse belong '
                      'on this trail? 0 = no, 1 = related, 2 = yes.</small></div>']
    for i, (title, mood, seed, mgenes) in enumerate(trails):
        verses = play(eng, seed, mgenes)
        key[str(i)] = {'title': title, 'mood': mood, 'verses': verses}
        sub = f' &middot; mood: {html.escape(moods[mood]["label"])}' if mood else ''
        parts.append(f'<h2>{i + 1}. {html.escape(title)}{sub}</h2>')
        for v in verses:
            t = content.execute('SELECT text FROM text_english WHERE verse_id = ?', (v,)).fetchone()[0]
            parts.append(f'<div class="p"><div class="r">{html.escape(ref(v))}</div><div>{html.escape(t)}</div><div>' + ''.join(
                f'<label><input type="radio" name="q{i}_{v}" value="{s}" onchange="mark({i},{v},{s})"> {s}</label>' for s in (0, 1, 2)) + '</div></div>')
        print(f'{i + 1}/{len(trails)} {title}: {len(verses)} verses', flush=True)
    parts.append("""<script>
const J=JSON.parse(localStorage.getItem('trailreview')||'{}');
function mark(q,v,s){J[q+'|'+v]=s;localStorage.setItem('trailreview',JSON.stringify(J));count();}
function count(){document.getElementById('done').textContent=Object.keys(J).length;}
for(const k in J){const [q,v]=k.split('|');const el=document.querySelector(`input[name="q${q}_${v}"][value="${J[k]}"]`);if(el)el.checked=true;}
count();
function save(){const b=new Blob([JSON.stringify(J,null,1)],{type:'application/json'});const a=document.createElement('a');
a.href=URL.createObjectURL(b);a.download='trail-judgments.json';a.click();}
</script>""")
    OUT.mkdir(exist_ok=True)
    (OUT / 'trail-review.html').write_text('\n'.join(parts), 'utf-8')
    (OUT / 'trail-review-key.json').write_text(json.dumps(key), 'utf-8')
    print(f'-> {OUT / "trail-review.html"}')


def score(path):
    j = json.loads(Path(path).read_text('utf-8'))
    key = json.loads((OUT / 'trail-review-key.json').read_text('utf-8'))
    per_mood, total, good, yes = {}, 0, 0, 0
    for i, t in key.items():
        marks = [j.get(f'{i}|{v}') for v in t['verses']]
        done = [m for m in marks if m is not None]
        if not done:
            continue
        g, y = sum(m >= 1 for m in done), sum(m == 2 for m in done)
        print(f"{t['title']:36s} related+ {g}/{len(done)}  yes {y}/{len(done)}")
        m = per_mood.setdefault(t['mood'] or '(none)', [0, 0, 0])
        m[0] += g
        m[1] += y
        m[2] += len(done)
        total += len(done)
        good += g
        yes += y
    print(f'\noverall: related-or-better {good}/{total} = {good / max(1, total):.2f}, clearly belongs {yes / max(1, total):.2f}')
    for k, (g, y, n) in sorted(per_mood.items()):
        print(f'  {k:12s} related+ {g / n:.2f}   yes {y / n:.2f}   (n={n})')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--score')
    a = ap.parse_args()
    score(a.score) if a.score else make()
