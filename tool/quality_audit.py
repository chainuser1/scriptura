"""Human audit of the entity and answers packs: the only honest way to claim 99%.

  .venv\\Scripts\\python.exe -I tool/quality_audit.py            # writes local-benchmarks/quality-audit.html (+ key)
  .venv\\Scripts\\python.exe -I tool/quality_audit.py --score F   # F = the exported judgments JSON

Three samples, each judged yes / no by a person (the sheet contains scripture text, so it stays in local-benchmarks/):
  links    entity <-> verse: "is this verse really about / naming this person, place or group?"
  identity entity description: "is the name, type and description right?"
  answers  verse <-> question: "does this passage genuinely speak to this question?"

Scoring reports accuracy and the Wilson 95% lower bound per sample against the 99% target, and lists every failure so the
rule that let it through can be fixed (or the entity added to tool/data/entity_overrides.json).
"""
import argparse
import html
import json
import math
import random
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEN = ROOT / 'generated-artifacts'
OUT = ROOT / 'local-benchmarks'
N_LINKS, N_IDENTITY, N_ANSWERS = 300, 400, 300  # identity is a census when fewer entities ship; 300 items bound the error at ~1.5% even with none
QUICK = (120, 80, 120)                          # a spot check: shows trouble, cannot certify 99%
TARGET = 0.99


def wilson_lower(ok, n, z=1.96):
    if n == 0:
        return 0.0
    p = ok / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    return (c - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d


def make(seed, sizes):
    n_links, n_identity, n_answers = sizes
    rng = random.Random(seed)
    ent = sqlite3.connect(f'file:{(GEN / "entities-pack-v1" / "entities.db").as_posix()}?mode=ro', uri=True)
    ans = sqlite3.connect(f'file:{(GEN / "answers-pack-v1" / "answers.db").as_posix()}?mode=ro', uri=True)
    content = sqlite3.connect(f'file:{(GEN / "release" / "content.db").as_posix()}?mode=ro', uri=True)
    cat = sqlite3.connect(f'file:{(GEN / "release" / "catalog.db").as_posix()}?mode=ro', uri=True)
    import bisect
    chapters = cat.execute('SELECT book_id, chapter, first_verse_id FROM chapters ORDER BY first_verse_id').fetchall()
    firsts = [c[2] for c in chapters]
    names = dict(cat.execute('SELECT book_id, name FROM book_names_english'))

    def ref(v):
        b, ch, lo = chapters[bisect.bisect_right(firsts, v) - 1]
        return f'{names[b]} {ch}:{v - lo + 1}'

    def text(v):
        return content.execute('SELECT text FROM text_english WHERE verse_id = ?', (v,)).fetchone()[0]

    people = ent.execute('SELECT entity_id, name, qualifier, description, verse_count, corroborated FROM people').fetchall()
    # links: stratified by kind so places and groups are not drowned by people
    links = []
    for kind, n in (('person', n_links // 3), ('place', n_links // 3), ('group', n_links - 2 * (n_links // 3))):
        ids = [p[0] for p in people if p[0].startswith(kind + ':')]
        pairs = []
        for _ in range(n):
            eid = rng.choice(ids)
            v = rng.choice([r[0] for r in ent.execute('SELECT verse_id FROM person_verses WHERE entity_id = ?', (eid,))])
            pairs.append((eid, v))
        links += pairs
    names_by_id = {p[0]: p for p in people}
    identity = rng.sample(people, min(n_identity, len(people)))
    rows = ans.execute('SELECT verse_id, q_id, score FROM verse_question').fetchall()
    texts = dict(ans.execute("SELECT q_id, text FROM question_text WHERE language = 'english'"))
    answers = rng.sample(rows, min(n_answers, len(rows)))

    key = {'links': [[e, v] for e, v in links], 'identity': [p[0] for p in identity], 'answers': [[v, q] for v, q, _ in answers]}
    parts = ['<!doctype html><meta charset="utf-8"><title>Quality audit</title>'
             '<style>body{font:16px/1.5 system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem}'
             'h2{margin-top:2.5rem;border-bottom:2px solid #d3167b}.i{padding:.6rem 0;border-bottom:1px dotted #ccc}'
             '.t{color:#444}.e{font-weight:600}.q{font-style:italic}#bar{position:sticky;top:0;background:#fff;padding:.5rem 0;'
             'border-bottom:2px solid #0e183e}label{margin-right:1.2rem}</style>'
             '<div id="bar"><b>Quality audit</b> &middot; <span id="done">0</span> judged &middot; '
             '<button onclick="save()">Download judgments (JSON)</button> <small>Progress is saved in this browser.</small></div>']
    parts.append('<h2>A. Links: is this verse really about, or naming, the entity?</h2>')
    for i, (e, v) in enumerate(links):
        p = names_by_id[e]
        kind = e.split(':')[0]
        parts.append(f'<div class="i"><div class="e">{html.escape(p[1])} <small>({kind}{": " + html.escape(p[2]) if p[2] else ""})</small></div>'
                     f'<div class="t"><b>{html.escape(ref(v))}</b> {html.escape(text(v))}</div>'
                     + radios(f'links|{i}') + '</div>')
    parts.append('<h2>B. Identity: are the name, type and description right?</h2>')
    for i, p in enumerate(identity):
        kind = p[0].split(':')[0]
        parts.append(f'<div class="i"><div class="e">{html.escape(p[1])}</div><div class="t">type: <b>{kind}</b> &middot; '
                     f'{html.escape(p[2])} &middot; {html.escape(p[3])} &middot; {p[4]} verses</div>' + radios(f'identity|{i}') + '</div>')
    parts.append('<h2>C. Answers: does this passage genuinely speak to this question?</h2>')
    for i, (v, q, sc) in enumerate(answers):
        parts.append(f'<div class="i"><div class="q">{html.escape(texts[q])}</div>'
                     f'<div class="t"><b>{html.escape(ref(v))}</b> {html.escape(text(v))}</div>' + radios(f'answers|{i}') + '</div>')
    parts.append("""<script>
const J=JSON.parse(localStorage.getItem('qaudit')||'{}');
function mark(k,v){J[k]=v;localStorage.setItem('qaudit',JSON.stringify(J));count();}
function count(){document.getElementById('done').textContent=Object.keys(J).length;}
for(const k in J){const el=document.querySelector(`input[name="${k}"][value="${J[k]}"]`);if(el)el.checked=true;}
count();
function save(){const b=new Blob([JSON.stringify(J,null,1)],{type:'application/json'});const a=document.createElement('a');
a.href=URL.createObjectURL(b);a.download='quality-judgments.json';a.click();}
</script>""")
    OUT.mkdir(exist_ok=True)
    (OUT / 'quality-audit.html').write_text('\n'.join(parts), 'utf-8')
    (OUT / 'quality-audit-key.json').write_text(json.dumps(key), 'utf-8')
    print(f'{len(links)} links, {len(identity)} identities, {len(answers)} answers -> {OUT / "quality-audit.html"}')


def radios(name):
    return ('<div>' + ''.join(f'<label><input type="radio" name="{name}" value="{v}" onchange="mark(\'{name}\',\'{v}\')"> {t}</label>'
                              for v, t in (('1', 'yes'), ('0', 'no'))) + '</div>')


def score(path):
    judged = json.loads(Path(path).read_text('utf-8'))
    key = json.loads((OUT / 'quality-audit-key.json').read_text('utf-8'))
    ok = True
    for section, label in (('links', 'entity-verse links'), ('identity', 'entity identity'), ('answers', 'answers')):
        n = good = 0
        fails = []
        for i, item in enumerate(key[section]):
            j = judged.get(f'{section}|{i}')
            if j is None:
                continue
            n += 1
            good += int(j == '1')
            if j != '1':
                fails.append(item)
        if n == 0:
            print(f'{label:20s} not judged')
            continue
        lo = wilson_lower(good, n)
        verdict = 'PASS' if lo >= TARGET else 'below target'
        print(f'{label:20s} {good}/{n} = {good / n:.3f}  95% lower bound {lo:.3f}  [{verdict} at {TARGET:.0%}]')
        ok &= lo >= TARGET
        for f in fails[:15]:
            print('    no:', f)
    print('\nnote: a 99% lower bound needs about 400 judged items with at most 1 error; fewer items cannot certify it.')
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--score', help='exported judgments JSON')
    ap.add_argument('--seed', type=int, default=11)
    ap.add_argument('--quick', action='store_true', help='smaller spot-check sample')
    a = ap.parse_args()
    if a.score:
        return score(a.score)
    make(a.seed, QUICK if a.quick else (N_LINKS, N_IDENTITY, N_ANSWERS))
    return 0


if __name__ == '__main__':
    sys.exit(main())
