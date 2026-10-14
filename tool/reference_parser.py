"""Scripture reference parser reference implementation (PLAN 6.4, ENGINE_PLAN C3).

Resolves text such as "John 3:16", "Jn 3:16-18", "1 John 4", "Salmos 23", "D&C 64:7", "Alma 32-34",
"Genesis 1:31-2:3" and a bare book name against catalog.db's per-language aliases.

Contract the native engine must reproduce:
  * the book alias is resolved in the active language first, then English, then every other catalog language;
    the first tier with a hit decides; several different books inside the last tier => status 'ambiguous'
    with candidates (never a silent guess)
  * references are validated against the catalog: unknown chapter or verse => 'out_of_range' (never clamped)
  * output is verse-ID ranges, so the caller never does verse_id arithmetic
  * text that is not a reference => 'not_a_reference' (the UI then treats it as a search query; no hidden overrides)
  * separators accepted: ':' '.' ',' between chapter and verse; '-' '–' '—' for ranges
  * not accepted: no space between book and numbers ("Jn3:16")

  .venv\\Scripts\\python.exe -I tool/reference_parser.py CATALOG.db "John 3:16" --language english
"""
import argparse
import json
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

LANGS = ('english', 'spanish', 'tagalog', 'cebuano', 'greek', 'french', 'german', 'hebrew')
SEP = r'\s*[:.,]\s*'
DASH = r'\s*[-–—]\s*'
PATTERNS = (
    # chapter:verse-chapter:verse
    ('range_x', re.compile(rf'^(?P<c1>\d+){SEP}(?P<v1>\d+){DASH}(?P<c2>\d+){SEP}(?P<v2>\d+)$')),
    # chapter:verse-verse
    ('range', re.compile(rf'^(?P<c1>\d+){SEP}(?P<v1>\d+){DASH}(?P<v2>\d+)$')),
    # chapter:verse
    ('verse', re.compile(rf'^(?P<c1>\d+){SEP}(?P<v1>\d+)$')),
    # chapter-chapter
    ('chapters', re.compile(rf'^(?P<c1>\d+){DASH}(?P<c2>\d+)$')),
    # chapter
    ('chapter', re.compile(r'^(?P<c1>\d+)$')),
)


def fold(s):
    s = unicodedata.normalize('NFC', s).lower().replace('—', '--').replace('’', "'")
    return re.sub(r'\s+', ' ', s).strip()


def strip_marks(s):
    return unicodedata.normalize('NFC', ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn'))


def alias_keys(text):
    base = re.sub(r'\s+', ' ', fold(text).replace('.', '')).strip()
    keys = [base, strip_marks(base), re.sub(r'^(\d)\s+', r'\1', base)]
    seen, out = set(), []
    for k in keys:
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


class Catalog:
    def __init__(self, path):
        c = sqlite3.connect(f'file:{Path(path).as_posix()}?mode=ro', uri=True)
        self.meta = dict(c.execute('SELECT key, value FROM catalog_meta'))
        self.languages = [l for l in self.meta['served_languages'].split(',') if l]
        self.books = {r[0]: {'name': r[1], 'first': r[2], 'last': r[3], 'chapters': r[4]}
                      for r in c.execute('SELECT book_id, canonical_name, first_verse_id, last_verse_id, chapter_count FROM books')}
        self.chapters = {(r[0], r[1]): (r[2], r[3]) for r in c.execute('SELECT book_id, chapter, first_verse_id, last_verse_id FROM chapters')}
        self.aliases = {}
        for lang in self.languages:
            assert lang in LANGS
            self.aliases[lang] = dict(c.execute(f'SELECT alias, book_id FROM book_aliases_{lang}'))

    def lookup(self, text, language):
        """-> (tier_language, [book_ids]) or (None, [])."""
        order = [language] + (['english'] if language != 'english' else [])
        others = [l for l in self.languages if l not in order]
        tiers = [[l] for l in order if l in self.aliases] + ([others] if others else [])
        for tier in tiers:
            hits = []
            for lang in tier:
                for key in alias_keys(text):
                    b = self.aliases.get(lang, {}).get(key)
                    if b is not None:
                        if b not in hits:
                            hits.append(b)
                        break
            if hits:
                return tier[0], hits
        return None, []


def parse(catalog, text, language='english'):
    s = fold(text)
    if not s:
        return {'status': 'not_a_reference', 'input': text}
    tokens = s.split(' ')
    # try the shortest numeric suffix that leaves a resolvable book prefix
    for i in range(len(tokens) - 1, 0, -1):
        prefix, suffix = ' '.join(tokens[:i]), ' '.join(tokens[i:])
        for kind, pat in PATTERNS:
            m = pat.match(suffix)
            if not m:
                continue
            tier, books = catalog.lookup(prefix, language)
            if not books:
                break
            return _resolve(catalog, text, tier, books, kind, {k: int(v) for k, v in m.groupdict().items()})
    tier, books = catalog.lookup(s, language)
    if books:
        return _resolve(catalog, text, tier, books, 'book', {})
    return {'status': 'not_a_reference', 'input': text}


def _resolve(catalog, text, tier, books, kind, n):
    if len(books) > 1:
        return {'status': 'ambiguous', 'input': text,
                'candidates': [{'book_id': b, 'book': catalog.books[b]['name']} for b in books]}
    bid = books[0]
    book = catalog.books[bid]
    out = {'status': 'ok', 'input': text, 'matched_language': tier, 'book_id': bid, 'book': book['name'], 'kind': kind}

    def chap(c):
        r = catalog.chapters.get((bid, c))
        return r

    def bad(msg):
        return {'status': 'out_of_range', 'input': text, 'book_id': bid, 'book': book['name'], 'kind': kind, 'reason': msg}

    if kind == 'book':
        out.update(first_verse_id=book['first'], last_verse_id=book['last'])
        return out
    c1 = chap(n['c1'])
    if c1 is None:
        return bad(f"{book['name']} has {book['chapters']} chapters, not {n['c1']}")
    if kind == 'chapter':
        out.update(chapter=n['c1'], first_verse_id=c1[0], last_verse_id=c1[1])
        return out
    if kind == 'chapters':
        c2 = chap(n['c2'])
        if c2 is None or n['c2'] < n['c1']:
            return bad(f"chapter range {n['c1']}-{n['c2']} is not valid in {book['name']}")
        out.update(chapter=n['c1'], chapter_end=n['c2'], first_verse_id=c1[0], last_verse_id=c2[1])
        return out
    v1 = n['v1']
    if not 1 <= v1 <= c1[1] - c1[0] + 1:
        return bad(f"{book['name']} {n['c1']} has {c1[1] - c1[0] + 1} verses, not {v1}")
    first = c1[0] + v1 - 1
    if kind == 'verse':
        out.update(chapter=n['c1'], verse=v1, first_verse_id=first, last_verse_id=first)
        return out
    c2n = n.get('c2', n['c1'])
    c2 = chap(c2n)
    if c2 is None:
        return bad(f"{book['name']} has {book['chapters']} chapters, not {c2n}")
    v2 = n['v2']
    if not 1 <= v2 <= c2[1] - c2[0] + 1:
        return bad(f"{book['name']} {c2n} has {c2[1] - c2[0] + 1} verses, not {v2}")
    last = c2[0] + v2 - 1
    if last < first:
        return bad('range ends before it starts')
    out.update(chapter=n['c1'], verse=v1, chapter_end=c2n, verse_end=v2, first_verse_id=first, last_verse_id=last)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('catalog')
    ap.add_argument('text')
    ap.add_argument('--language', default='english')
    a = ap.parse_args()
    print(json.dumps(parse(Catalog(a.catalog), a.text, a.language), ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
