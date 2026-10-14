"""Gated person linking: "Who is Captain Moroni?" -> person:moroni_captain, never the other Moroni.

Source: the legacy AI people index (verse-tags.db, quality unreviewed). Gating rules, each measurable in
test/entity_linker_check.py:

  1. only people with >= MIN_VERSES tagged verses are linkable (the long tail is mostly extraction noise);
  2. 'generic' people (> GENERIC_SHARE of the corpus: Jesus Christ, God the Father) are recognised but never used as a
     verse filter, because a filter that keeps 18% of the Bible filters nothing;
  3. same-name people are separated by qualifier words in the question; qualifiers are matched across English,
     Spanish, Tagalog, Cebuano and Greek through a small hand-written equivalence table (QUALIFIER_WORDS);
  4. with no discriminating word, a person with >= DOMINANCE x the verses of the runner-up wins ("Who was Moses?"),
     otherwise the answer is 'ambiguous' and the app shows one chip per candidate.

  .venv\\Scripts\\python.exe -I tool/entity_linker.py --export generated-artifacts/release/entities.db
"""
import argparse
import json
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Source of the people tags. The project no longer carries the legacy databases; the phase-0 backup keeps them.
LEGACY_DB = next((p for p in (
    ROOT / 'legacy-quarantine' / 'resources' / 'db' / 'verse-tags.db',
    ROOT.parent / 'scriptura' / 'app-backups' / 'scriptures_reader_mobile-before-phase0-20261011' / 'assets' / 'resources' / 'db' / 'verse-tags.db',
) if p.exists()), ROOT / 'legacy-quarantine' / 'resources' / 'db' / 'verse-tags.db')
TOTAL_VERSES = 41995
MIN_VERSES = 8
GENERIC_SHARE = 0.05
DOMINANCE = 3.0

_WORDS = json.loads((ROOT / 'engine' / 'data' / 'entity_linker_words.json').read_text('utf-8'))
STOP = set(_WORDS['stop'])
TITLE_ONLY = set(_WORDS['title_only'])      # profiles named only by a title ('King', 'the angel') are never link targets
QUALIFIER_WORDS = _WORDS['qualifier_words']  # English qualifier word -> equivalent question words in other languages
PERSON_QUESTION = _WORDS['person_question']  # matched against the accent-folded, lower-cased question
PLACE_QUESTION = _WORDS['place_question']    # "Where is ...": places only
ABOUT_QUESTION = _WORDS['about_question']    # "Tell me about ...": people, groups and places


def fold(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s.lower()) if unicodedata.category(c) != 'Mn')


_STOP_FOLDED = {fold(x) for x in STOP}
_TO_ENGLISH = {w: en for en, ws in QUALIFIER_WORDS.items() for w in ws}


def tokens(s):
    return [t for t in re.findall(r"[\w']+", fold(s)) if t not in _STOP_FOLDED]


def is_person_question(q):
    f = fold(q).strip().lstrip('¿¡')
    return any(re.match(p, f) for p in PERSON_QUESTION)


def question_kinds(q):
    """Entity kinds a question may be about: 'who' -> people and groups, 'where' -> places, 'tell me about' -> all."""
    f = fold(q).strip().lstrip('¿¡')
    if any(re.match(p, f) for p in PERSON_QUESTION):
        return ('person', 'group')
    if any(re.match(p, f) for p in PLACE_QUESTION):
        return ('place',)
    if any(re.match(p, f) for p in ABOUT_QUESTION):
        return ('person', 'group', 'place')
    return None


class PeopleIndex:
    def __init__(self, db=LEGACY_DB, export=False):
        """db: the legacy tag index (people only, filtered here) or, with export=True, a published entities.db."""
        c = sqlite3.connect(f'file:{Path(db).as_posix()}?mode=ro&immutable=1', uri=True)
        self.profiles = {}
        if export:
            rows = c.execute('SELECT entity_id, name, qualifier, description, verse_count FROM people')
        else:
            rows = c.execute("SELECT entity_id, name, qualifier, description, verse_count FROM ai_entity_profiles WHERE type = 'person'")
        for eid, name, qual, desc, n in rows:
            if not export and n < MIN_VERSES:
                continue
            q_tok = set(tokens(f'{qual or ""} {desc or ""}'))
            name_tok = set(tokens(name.split(',')[0]))
            slug_tok = set(tokens(eid.split(':', 1)[1].replace('_', ' ')))
            self.profiles[eid] = {'name': name, 'qualifier': qual or '', 'description': desc or '', 'n': n, 'name_tok': name_tok,
                                  'slug_tok': slug_tok, 'qual_tok': q_tok - name_tok,
                                  'generic': n > GENERIC_SHARE * TOTAL_VERSES}
        self.verses = {}
        verse_rows = c.execute('SELECT entity_id, verse_id FROM person_verses') if export else \
            c.execute("SELECT entity_id, verse_id FROM ai_entity_verse_map WHERE entity_id LIKE 'person:%'")
        for eid, vid in verse_rows:
            if eid in self.profiles:
                self.verses.setdefault(eid, []).append(vid)

    def link(self, query):
        """-> {'status': none|single|ambiguous|generic, 'candidates': [entity_id, ...], 'filter': bool}

        'filter' tells the ranker whether the entity's verses may be used to constrain/boost results."""
        kinds = question_kinds(query)
        if kinds is None:
            return {'status': 'none', 'candidates': [], 'filter': False}
        q = set(tokens(query))
        q_en = q | {_TO_ENGLISH[t] for t in q if t in _TO_ENGLISH}
        found = [e for e, p in self.profiles.items()
                 if e.split(':', 1)[0] in kinds and
                 ((p['name_tok'] and p['name_tok'] <= q_en and not p['name_tok'] <= TITLE_ONLY)
                  or (p['slug_tok'] and p['slug_tok'] <= q_en and not p['slug_tok'] <= TITLE_ONLY))]
        if not found:
            return {'status': 'none', 'candidates': [], 'filter': False}

        def specificity(e):
            """words of the person's own id slug count double; qualifier words that merely name a sibling
            ("son of Alma the Elder" for the Younger) are ignored"""
            p = self.profiles[e]
            sib = set().union(*(self.profiles[o]['slug_tok'] for o in found if o != e))
            rest = q_en - p['name_tok']
            return 2 * len(rest & p['slug_tok']) + len(rest & (p['qual_tok'] - sib))
        score = {e: specificity(e) for e in found}
        # the person asked about is the one named first; several profiles may share it, so keep the longest name there
        order = [t for t in re.findall(r"[\w']+", fold(query))]

        def matched(e):
            p = self.profiles[e]
            return max((t for t in (p['name_tok'], p['slug_tok']) if t and t <= q_en), key=len, default=set())

        def first_pos(e):
            return min((order.index(t) for t in matched(e) if t in order), default=len(order))
        lead = min(found, key=lambda e: (first_pos(e), -len(matched(e))))
        key = (first_pos(lead), len(matched(lead)))
        found = [e for e in found if (first_pos(e), len(matched(e))) == key]
        score = {e: score[e] for e in found}
        found.sort(key=lambda e: (-score[e], -self.profiles[e]['n']))
        top, rest = found[0], found[1:]
        if len(found) == 1 or score[top] > score[rest[0]]:
            pick = [top]
        elif self.profiles[top]['n'] >= DOMINANCE * self.profiles[rest[0]]['n']:
            pick = [top]
        else:
            ties = [e for e in found if score[e] == score[top]]
            return {'status': 'ambiguous', 'candidates': ties[:3], 'filter': False}
        also = [e for e in found if e != pick[0]][:2]   # same-name people the app can offer as "also: ..."
        if self.profiles[pick[0]]['generic']:
            return {'status': 'generic', 'candidates': pick, 'filter': False, 'alternatives': also}
        return {'status': 'single', 'candidates': pick, 'filter': True, 'alternatives': also}

    def export(self, out):
        out = Path(out)
        out.unlink(missing_ok=True)
        c = sqlite3.connect(out)
        c.executescript("""
            PRAGMA journal_mode=OFF;
            CREATE TABLE people(entity_id TEXT PRIMARY KEY, name TEXT NOT NULL, qualifier TEXT NOT NULL,
                                description TEXT NOT NULL, verse_count INTEGER NOT NULL, generic INTEGER NOT NULL) WITHOUT ROWID;
            CREATE TABLE person_verses(entity_id TEXT NOT NULL, verse_id INTEGER NOT NULL,
                                       PRIMARY KEY(entity_id, verse_id)) WITHOUT ROWID;
            CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
        """)
        c.executemany('INSERT INTO people VALUES (?,?,?,?,?,?)',
                      [(e, p['name'], p['qualifier'], p['description'], p['n'], int(p['generic'])) for e, p in sorted(self.profiles.items())])
        c.executemany('INSERT INTO person_verses VALUES (?,?)',
                      [(e, v) for e, vs in sorted(self.verses.items()) for v in sorted(vs)])
        c.executemany('INSERT INTO meta VALUES (?,?)', [
            ('source', 'legacy AI people index verse-tags.db (machine-generated, not human reviewed)'),
            ('min_verses', str(MIN_VERSES)), ('generic_share', str(GENERIC_SHARE)), ('dominance', str(DOMINANCE))])
        c.commit()
        c.execute('VACUUM')
        c.close()
        return out.stat().st_size


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--export', help='write a compact entities.db here')
    ap.add_argument('query', nargs='*')
    a = ap.parse_args()
    idx = PeopleIndex()
    if a.export:
        print(f'{a.export}: {idx.export(a.export):,} bytes, {len(idx.profiles)} people')
    for q in a.query:
        print(q, '->', idx.link(q))
    return 0


if __name__ == '__main__':
    sys.exit(main())
