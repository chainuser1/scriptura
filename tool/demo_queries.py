"""Run realistic, user-style questions through several retrieval configurations and print what a person would see.

Methods: Experiment D, 90:10, Lean (genome+dense+sparse), Full (adds ColBERT), the best combination found by
tool/fusion_search.py, a two-lane view (wording lane + theme lane), and an EXPERIMENTAL entity-aware path that uses the
legacy AI people index (verse-tags.db, quarantined, quality unreviewed) to separate people who share a name.

  .venv\\Scripts\\python.exe -I tool/demo_queries.py [--only moroni] [--top 6]
Full output (with verse text, gitignored): local-benchmarks/demo_results.md
"""
import argparse
import re
import sqlite3
import sys
from pathlib import Path

import numpy as np
from scipy import sparse as sp
from transformers import AutoTokenizer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_quantized import Pack, variant_path  # noqa: E402
from quantize_onnx import encode, session  # noqa: E402
from reference_parser import Catalog as RefCatalog, parse as parse_ref  # noqa: E402
from reference_search import DEFAULT_EXTRACTED, VOCAB, Searcher, normalize_rows, top_rows, zscore  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RELEASE = ROOT / 'generated-artifacts' / 'release'
from entity_linker import LEGACY_DB as ENTITY_DB  # noqa: E402  (falls back to the phase-0 backup)

QUERIES = [
    ('names', 'Who is Captain Moroni?'),
    ('names', 'Who is Moroni the son of Mormon?'),
    ('names', 'Who was the prophet Moroni who buried the plates?'),
    ('names', 'Who was Nephi?'),
    ('names', 'Who is Alma the Younger?'),
    ('names', 'Who was Melchizedek?'),
    ('stories', "story of Daniel in the lions' den"),
    ('stories', 'How did Jesus feed the five thousand?'),
    ('stories', 'Why did Nephi build a ship?'),
    ('doctrine', 'What are the Ten Commandments?'),
    ('doctrine', 'What is the Word of Wisdom?'),
    ('doctrine', 'What did Jesus teach about forgiving others?'),
    ('personal', 'How do I overcome fear?'),
    ('personal', "I feel like I'm not good enough for God"),
    ('personal', 'My son has left the church. What can I do?'),
    ('phrase', 'ask and ye shall receive'),
    ('phrase', 'the Lord is my shepherd'),
    ('keyword', 'charity'),
    ('keyword', 'tithing blessings'),
    ('language', '¿Quién fue el capitán Moroni?'),
    ('language', 'Sino si Nephi?'),
    ('language', 'Ano ang sinasabi ng banal na kasulatan tungkol sa kapatawaran?'),
    ('reference', 'John 3:16'),
    ('reference', 'Alma 32'),
]
STOP = set('who is was the of a an and to in on for with what how why did do does i my me you your are be can have has from this that about said say'.split())


def tokens(s):
    return [t for t in re.findall(r"[\w']+", s.lower()) if t not in STOP]


class Entities:
    """Legacy AI people index. Profiles carry a qualifier/description that disambiguates shared names."""

    def __init__(self):
        c = sqlite3.connect(f'file:{ENTITY_DB.as_posix()}?mode=ro&immutable=1', uri=True)
        self.profiles = {}
        for eid, name, typ, qual, desc, vc in c.execute(
                "SELECT entity_id, name, type, qualifier, description, verse_count FROM ai_entity_profiles WHERE type = 'person'"):
            self.profiles[eid] = {'name': name, 'qualifier': qual, 'desc': desc, 'n': vc,
                                  'tok': set(tokens(f'{qual} {desc}')), 'name_tok': set(tokens(name))}
        self.verses = {}
        for eid, vid in c.execute("SELECT entity_id, verse_id FROM ai_entity_verse_map WHERE entity_id LIKE 'person:%'"):
            self.verses.setdefault(eid, []).append(vid)

    def link(self, query):
        """-> ('none'|'single'|'ambiguous', [(entity_id, score)]) by name match plus qualifier/description overlap."""
        q = set(tokens(query))
        found = [eid for eid, p in self.profiles.items() if p['name_tok'] and p['name_tok'] <= q and p['n'] >= 8]
        if not found:
            return 'none', []
        scored = sorted(((eid, len(q & self.profiles[eid]['tok'] - self.profiles[eid]['name_tok'])) for eid in found),
                        key=lambda x: (-x[1], -self.profiles[x[0]]['n']))
        # same name, different people: need a discriminating word, else show every candidate
        names = {self.profiles[e]['name'] for e, _ in scored}
        if len(scored) == 1:
            return 'single', scored
        if scored[0][1] > scored[1][1]:
            return 'single', scored[:1]
        return 'ambiguous', scored if len(names) <= 2 else scored[:3]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--only', default='')
    ap.add_argument('--top', type=int, default=6)
    ap.add_argument('--variant', default='int8_matmul')
    a = ap.parse_args()

    s = Searcher(DEFAULT_EXTRACTED, encoder=object())
    with np.load(DEFAULT_EXTRACTED / 'scripture-genome-question-hidden4096-optimized' / 'head_fp16.npz', allow_pickle=False) as z:
        s.head = {'0.weight': z['w0'].astype(np.float32), '0.bias': z['b0'].astype(np.float32),
                  '2.weight': z['w1'].astype(np.float32), '2.bias': z['b1'].astype(np.float32)}
    wg = normalize_rows(np.load(DEFAULT_EXTRACTED / 'scripture-retrieval-english-v1' / 'weighted_genome_embeddings.f16.npy',
                                allow_pickle=False).astype(np.float32))
    tok = AutoTokenizer.from_pretrained(DEFAULT_EXTRACTED / 'bge-m3-pinned')
    unused = {tok.cls_token_id, tok.eos_token_id, tok.pad_token_id, tok.unk_token_id}
    pack, sess, vids = Pack(), session(variant_path(a.variant)), s.verse_ids
    row_of = {int(v): i for i, v in enumerate(vids)}
    content = sqlite3.connect(f'file:{(RELEASE / "content.db").as_posix()}?mode=ro', uri=True)
    text_en = dict(content.execute('SELECT verse_id, text FROM text_english'))
    cat = sqlite3.connect(f'file:{(RELEASE / "catalog.db").as_posix()}?mode=ro', uri=True)
    chapters = cat.execute('SELECT book_id, chapter, first_verse_id FROM chapters ORDER BY first_verse_id').fetchall()
    names = dict(cat.execute('SELECT book_id, name FROM book_names_english'))
    import bisect
    firsts = [c[2] for c in chapters]

    def ref(v):
        bid, ch, lo = chapters[bisect.bisect_right(firsts, v) - 1]
        return f'{names[bid]} {ch}:{v - lo + 1}'

    refcat = RefCatalog(RELEASE / 'catalog.db')
    ents = Entities()
    W = {'Experiment D': (0.28, 0.14, 0.28, 0.30), 'Lean g80': (0.10, 0.10, 0.0, 0.80), 'Full g80+ColBERT': (0.05, 0.0, 0.15, 0.80)}

    out_md = ['# Demo results (local only; contains verse text)\n']
    queries = [q for q in QUERIES if a.only.lower() in q[1].lower()]
    for group, q in queries:
        line = f'\n=== [{group}] {q}'
        print(line)
        out_md.append(f'\n## [{group}] {q}\n')
        r = parse_ref(refcat, q, 'english')
        if r['status'] == 'ok':
            msg = f"  -> reference jump: {r['book']} {r.get('chapter', '')}  verses {ref(r['first_verse_id'])} .. {ref(r['last_verse_id'])}"
            print(msg)
            out_md.append(msg + '\n')
            continue
        dense, sparse, col, _ = encode(sess, tok, [q], unused, batch=1)
        d = dense[0]
        da = (s.dense @ d).astype(np.float64)
        ga = (wg @ normalize_rows((s.genome_of(d) * s.sw)[None, :])[0]).astype(np.float64)
        qs = sp.lil_matrix((1, VOCAB), dtype=np.float32)
        for t, x in sparse[0].items():
            qs[0, t] = x
        sa = (s.csr @ qs.tocsr().T).toarray().ravel().astype(np.float64)
        cand = np.unique(np.concatenate([top_rows(x, vids, 200) for x in (da, sa, ga)]))
        ca = pack.maxsim(col[0], cand)
        Z = np.stack([zscore(da[cand]), zscore(sa[cand]), zscore(ca), zscore(ga[cand])])
        cid = vids[cand]
        lists = {}
        for name, w in W.items():
            lists[name] = [int(cid[i]) for i in np.lexsort((cid, -(np.array(w) @ Z)))[:a.top]]
        lists['90:10'] = [int(vids[i]) for i in top_rows(0.9 * zscore(ga) + 0.1 * zscore(da), vids, a.top)]
        lists['Text lane (wording)'] = [int(cid[i]) for i in np.lexsort((cid, -(np.array([.4, .2, .4, 0]) @ Z)))[:a.top]]
        lists['Theme lane (genome)'] = [int(cid[i]) for i in np.lexsort((cid, -Z[3]))[:a.top]]

        status, linked = ents.link(q)
        if status != 'none':
            groups = []
            for eid, _sc in linked:
                ev = [v for v in ents.verses.get(eid, []) if v in row_of]
                rows = np.array([row_of[v] for v in ev])
                sc = (np.array([0.10, 0.10, 0.0, 0.80]) @ np.stack([zscore(da[rows]), zscore(sa[rows]), np.zeros(len(rows)), zscore(ga[rows])]))
                top = [int(vids[rows[i]]) for i in np.lexsort((vids[rows], -sc))[:a.top]]
                groups.append((eid, ents.profiles[eid]['qualifier'], top, len(ev)))
        for name, lst in lists.items():
            refs = ' | '.join(ref(v) for v in lst)
            print(f'  {name:22s} {refs}')
            out_md.append(f'**{name}**\n' + '\n'.join(f'- {ref(v)} — {text_en.get(v, "")}' for v in lst) + '\n')
        if status != 'none':
            tag = 'single' if status == 'single' else 'AMBIGUOUS (no discriminating word) - show both'
            print(f'  [experimental entity-aware: {tag}]')
            for eid, qual, top, n in groups:
                print(f'    {eid} ({n} verses): {qual}')
                print('      ' + ' | '.join(ref(v) for v in top))
                out_md.append(f'**Entity: {eid}** — {qual}\n' + '\n'.join(f'- {ref(v)} — {text_en.get(v, "")}' for v in top) + '\n')
    out = ROOT / 'local-benchmarks' / 'demo_results.md'
    out.parent.mkdir(exist_ok=True)
    out.write_text('\n'.join(out_md), 'utf-8')
    print('\nfull results with verse text:', out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
