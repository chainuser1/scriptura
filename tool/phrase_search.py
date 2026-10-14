"""Model-free phrase search reference (PLAN 6.4, ENGINE_PLAN C2).

Semantics (the contract the native engine must reproduce):
  * the whole input is ONE phrase: consecutive words, in order
  * case-insensitive; accents are preserved (no diacritic folding); no stemming, synonyms or implicit OR
  * FTS5 operators are never interpreted: operator WORDS (AND, OR, NOT, NEAR) are searched as ordinary words and
    operator CHARACTERS (* ^ : - " ( )) are plain punctuation that the tokenizer ignores
  * text and queries are NFC-normalized (FTS5 unicode61 treats combining marks as separators)
  * results are in canonical verse order; the total match count is reported; only the SELECTED language is searched
  * only languages the content database declares complete are indexed/served

  .venv\\Scripts\\python.exe -I tool/phrase_search.py build CONTENT.db OUT.db
  .venv\\Scripts\\python.exe -I tool/phrase_search.py search PHRASE --db OUT.db [--language english] [--top-k 20]
"""
import argparse
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

LANGS = ('english', 'spanish', 'tagalog', 'cebuano', 'greek', 'french', 'german', 'hebrew')  # SQL-safety allowlist
TOKENIZE = "unicode61 remove_diacritics 0"
FTS_OPTIONS = 'columnsize=0'  # no bm25 here, so per-column sizes are dead weight (about 11% smaller, same hits)


class PhraseError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _nfc(s):
    return unicodedata.normalize('NFC', s)


def build_index(content_db, out_db):
    """One contentless FTS5 table per complete language; rowid == verse_id."""
    out_db = Path(out_db)
    if out_db.exists():
        raise FileExistsError(out_db)
    src = sqlite3.connect(f'file:{Path(content_db).as_posix()}?mode=ro', uri=True)
    cov = {r[0]: r[1] for r in src.execute('SELECT language, table_name FROM language_coverage WHERE complete = 1')}
    tmp = out_db.with_suffix(out_db.suffix + '.tmp')
    if tmp.exists():
        tmp.unlink()
    dst = sqlite3.connect(tmp)
    dst.execute('CREATE TABLE phrase_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID')
    built = []
    for lang in LANGS:
        if lang not in cov:
            continue
        dst.execute(f'CREATE VIRTUAL TABLE phrase_{lang} USING fts5(text, content="", tokenize="{TOKENIZE}", {FTS_OPTIONS})')
        rows = src.execute(f'SELECT verse_id, scripture_text FROM {cov[lang]} ORDER BY verse_id').fetchall()
        dst.executemany(f'INSERT INTO phrase_{lang}(rowid, text) VALUES (?, ?)', [(v, _nfc(t)) for v, t in rows])
        dst.execute(f"INSERT INTO phrase_{lang}(phrase_{lang}) VALUES ('optimize')")
        built.append((lang, len(rows)))
    dst.executemany('INSERT INTO phrase_meta VALUES (?,?)', [
        ('tokenizer', TOKENIZE), ('languages', ','.join(l for l, _ in built)),
        ('rows', ','.join(f'{l}={n}' for l, n in built)),
        ('semantics', 'one phrase, consecutive words, case-insensitive, accents preserved, operators literal'),
    ])
    dst.commit()
    dst.execute('VACUUM')
    dst.close()
    src.close()
    tmp.replace(out_db)
    return built


def to_match(phrase):
    p = _nfc(phrase).strip()
    if not p:
        raise PhraseError('invalid_input', 'empty phrase')
    if not re.search(r'\w', p):
        raise PhraseError('invalid_input', 'phrase has no searchable words')
    return '"' + p.replace('"', '""') + '"'


def search(db, phrase, language='english', top_k=20, allowed_verse_ids=None):
    """-> {'verse_ids': [...canonical order...], 'total': int, 'truncated': bool}"""
    if language not in LANGS:
        raise PhraseError('unsupported_language', f'unknown language {language!r}')
    match = to_match(phrase)
    conn = db if isinstance(db, sqlite3.Connection) else sqlite3.connect(f'file:{Path(db).as_posix()}?mode=ro', uri=True)
    have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if f'phrase_{language}' not in have:
        raise PhraseError('unsupported_language', f'language {language!r} has no phrase index (not served)')
    ids = [r[0] for r in conn.execute(f'SELECT rowid FROM phrase_{language} WHERE phrase_{language} MATCH ? ORDER BY rowid', (match,))]
    if allowed_verse_ids is not None:
        allowed = set(allowed_verse_ids)
        ids = [i for i in ids if i in allowed]
    return {'verse_ids': ids[:top_k], 'total': len(ids), 'truncated': len(ids) > top_k}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('build')
    b.add_argument('content_db')
    b.add_argument('out_db')
    s = sub.add_parser('search')
    s.add_argument('phrase')
    s.add_argument('--db', required=True)
    s.add_argument('--language', default='english')
    s.add_argument('--top-k', type=int, default=20)
    a = ap.parse_args()
    if a.cmd == 'build':
        print('built', build_index(a.content_db, a.out_db))
    else:
        print(search(a.db, a.phrase, a.language, a.top_k))
    return 0


if __name__ == '__main__':
    sys.exit(main())
