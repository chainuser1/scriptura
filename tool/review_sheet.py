"""Pooled, anonymised review sheet for the human-judged evaluation (PLAN 12.1: at least 100 independently reviewed intents).

For each query the top 10 of every search profile are pooled, de-duplicated and shuffled; the reviewer sees only
passages (never which profile returned them) and marks each 0 = not relevant, 1 = related, 2 = directly answers.
The sheet is a single HTML file (it contains scripture text, so it goes to local-benchmarks/, gitignored). Judgments are
saved in the browser as you go and exported as JSON; tool/score_review.py turns them into per-profile metrics.

  .venv\\Scripts\\python.exe -I tool/review_sheet.py [--queries 120] [--seed 7]
"""
import argparse
import ctypes
import html
import json
import random
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEN = ROOT / 'generated-artifacts'
OUT = ROOT / 'local-benchmarks'
TOP = 10


class Engine:
    def __init__(self):
        lib = ctypes.CDLL(str(ROOT / 'engine' / 'target' / 'release' / 'scripture_engine.dll'))
        lib.se_open.restype = ctypes.c_void_p
        lib.se_open.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_char_p)]
        lib.se_request.restype = ctypes.c_void_p
        lib.se_request.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        lib.se_free_string.argtypes = [ctypes.c_void_p]
        self.lib = lib
        pack = GEN / 'engine-pack'
        m = json.loads((pack / 'manifest.json').read_text('utf-8'))
        colbert = GEN / 'colbert-pack-v1'
        cfg = {
            'retrieval_dir': str(pack / 'retrieval'), 'head_npz': str(pack / 'head.npz'),
            'encoder_model': str(pack / m['encoder_file']), 'tokenizer_json': str(pack / 'tokenizer.json'),
            'pack_dir': str(colbert), 'phrase_db': str(GEN / 'release' / 'phrase-index.db'),
            'catalog_db': str(GEN / 'release' / 'catalog.db'), 'entities_db': str(pack / 'entities.db'),
            'profiles': m['profiles'], 'default_profile': m['default_profile'],
            'fallback_without_thread': m['fallback_without_thread'], 'threads': 4, 'identity': m['identity'],
        }
        err = ctypes.c_char_p()
        self.h = lib.se_open(json.dumps(cfg).encode(), ctypes.byref(err))
        if not self.h:
            sys.exit(f'engine did not open: {err.value}')
        self.profiles = list(m['profiles'])

    def search(self, query, profile):
        req = json.dumps({'op': 'semantic', 'query': query, 'profile': profile, 'top_k': TOP}).encode()
        p = self.lib.se_request(self.h, req)
        out = json.loads(ctypes.string_at(p).decode())
        self.lib.se_free_string(p)
        if 'error' in out:
            raise RuntimeError(out['error'])
        return [h['verse_id'] for h in out['hits']]


def load_queries(n, rng):
    tset = json.loads((ROOT / 'tool' / 'intent_test_set.json').read_text('utf-8'))
    qs = [c['q'] for c in tset['comparison']]
    for items in tset['anchored'].values():
        qs += [i['q'] for i in items]
    qs += [p['q'] for p in tset['person']]
    rob = json.loads((ROOT / 'tool' / 'query_robustness_set.json').read_text('utf-8'))['intents']
    for it in rob:
        for kind in ('casual', 'formal'):
            v = it['variants'].get(kind)
            if v:
                qs.append(v['text'] if isinstance(v, dict) else v)
                break
    qs += json.loads((ROOT / 'tool' / 'review_queries_extra.json').read_text('utf-8'))['queries']
    seen, uniq = set(), []
    for q in qs:
        if q.lower() not in seen:
            seen.add(q.lower())
            uniq.append(q)
    rng.shuffle(uniq)
    return uniq[:n]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--queries', type=int, default=120)
    ap.add_argument('--seed', type=int, default=7)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    queries = load_queries(a.queries, rng)
    eng = Engine()
    content = sqlite3.connect(f'file:{(GEN / "release" / "content.db").as_posix()}?mode=ro', uri=True)
    cat = sqlite3.connect(f'file:{(GEN / "release" / "catalog.db").as_posix()}?mode=ro', uri=True)
    chapters = cat.execute('SELECT book_id, chapter, first_verse_id FROM chapters ORDER BY first_verse_id').fetchall()
    names = dict(cat.execute('SELECT book_id, name FROM book_names_english'))
    firsts = [c[2] for c in chapters]
    import bisect

    def ref(v):
        b, ch, lo = chapters[bisect.bisect_right(firsts, v) - 1]
        return f'{names[b]} {ch}:{v - lo + 1}'

    key, sections = {}, []
    for qi, q in enumerate(queries):
        ranks = {}
        for prof in eng.profiles:
            for r, v in enumerate(eng.search(q, prof)):
                ranks.setdefault(v, {})[prof] = r + 1
        pool = list(ranks)
        rng.shuffle(pool)
        key[str(qi)] = {'query': q, 'passages': {str(v): ranks[v] for v in pool}}
        rows = []
        for v in pool:
            text = content.execute('SELECT text FROM text_english WHERE verse_id = ?', (v,)).fetchone()[0]
            rows.append((v, ref(v), text))
        sections.append((qi, q, rows))
        print(f'{qi + 1}/{len(queries)} {q!r}: {len(pool)} pooled passages', flush=True)

    parts = ['<!doctype html><meta charset="utf-8"><title>Scripture search review</title>'
             '<style>body{font:16px/1.5 system-ui,sans-serif;max-width:860px;margin:2rem auto;padding:0 1rem}'
             'h2{margin-top:2.5rem;border-bottom:1px solid #ccc}.p{padding:.5rem 0;border-bottom:1px dotted #ddd}'
             '.r{font-weight:600}.opts label{margin-right:1rem}#bar{position:sticky;top:0;background:#fff;padding:.5rem 0;'
             'border-bottom:2px solid #333}</style>'
             '<div id="bar"><b>Review sheet</b> &middot; <span id="done">0</span> judged &middot; '
             '<button onclick="save()">Download judgments (JSON)</button> '
             '<small>0 = not relevant, 1 = related, 2 = directly answers the question. Progress is saved in this browser.</small></div>']
    for qi, q, rows in sections:
        parts.append(f'<h2>{qi + 1}. {html.escape(q)}</h2>')
        for v, r, text in rows:
            parts.append(
                f'<div class="p"><div class="r">{html.escape(r)}</div><div>{html.escape(text)}</div>'
                f'<div class="opts">' + ''.join(
                    f'<label><input type="radio" name="q{qi}_{v}" value="{s}" onchange="mark(\'{qi}\',\'{v}\',{s})"> {s}</label>'
                    for s in (0, 1, 2)) + '</div></div>')
    parts.append("""<script>
const J=JSON.parse(localStorage.getItem('review')||'{}');
function mark(q,v,s){J[q+'|'+v]=s;localStorage.setItem('review',JSON.stringify(J));count();}
function count(){document.getElementById('done').textContent=Object.keys(J).length;}
for(const k in J){const [q,v]=k.split('|');const el=document.querySelector(`input[name="q${q}_${v}"][value="${J[k]}"]`);if(el)el.checked=true;}
count();
function save(){const b=new Blob([JSON.stringify(J,null,1)],{type:'application/json'});const a=document.createElement('a');
a.href=URL.createObjectURL(b);a.download='review-judgments.json';a.click();}
</script>""")
    OUT.mkdir(exist_ok=True)
    (OUT / 'review-sheet.html').write_text('\n'.join(parts), 'utf-8')
    (OUT / 'review-key.json').write_text(json.dumps({'profiles': eng.profiles, 'top': TOP, 'queries': key}, indent=1), 'utf-8')
    total = sum(len(r) for _, _, r in sections)
    print(f'{len(queries)} queries, {total} passages to judge -> {OUT / "review-sheet.html"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
