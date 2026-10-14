"""Build entities-pack-v1: people, places and groups, purified for precision.

Source: the legacy AI entity index (verse-tags.db: names, types, qualifiers and tagged verses; machine-generated, kept
only in the phase-0 backup). Raw tags are noisy. The owner's yes/no audit of the first build (400 links, 300 identities)
measured 87% / 88%, and its failures name the causes; each rule below answers one:

  1. proper noun: the name starts with a capital letter and is not a bare common phrase ("the servants");
  2. grounded: a verse link is kept only when the entity's name (name or id-slug spelling) literally occurs in that
     verse's English text;
  3. attested: at least MIN_VERSES grounded verses survive;
  4. proper-noun behaviour: a single-word name must appear capitalised in >= CAPITALISED_SHARE of its grounded verses;
  5. type: person, place or group only; places whose description says month/calendar/festival are not places;
  6. homonym guard ("Johanan", "Zebadiah", "Philip", "John" share names with many bearers): unless the entity has at
     least 3x the tagged verses of all its same-named rivals (Moses), a link is kept only if the verse contains a word from
     its id slug that tells it apart (the father's name, "captain") or lies in a book that is this bearer's home and none
     of its rivals';
  7. cross-kind guard: a name shared by a person and a place ("Ammon", "Lehi", "Nephi", "Zebulun"): a place link needs a
     place cue just before the name (in/to/from/land of/city of...), and a person link is dropped inside "land of X";
  8. list guard: a link is dropped when the verse names more than 2 (people) or 3 (places, groups) other persons, and, for
     people, when it is genealogical ("begat", "son of"): identity is weakest there. A person needs >= 40 tagged verses
     (prominent people only; the minor same-named bearers of the genealogies cannot be told apart by name);
  8b. descriptions are not shipped: the audit found machine-written descriptions wrong in about one case in eight. The
     qualifier shown is read from the entity id slug (for example "son of Lehi"), or empty;
  9. duplicates merge: places and groups with the same name and the same (or no) qualifier are one entity;
 10. tool/data/entity_overrides.json (owner-editable) can drop an entity or replace a qualifier.

Corroboration (flag only): the name also names a topic in the Topical Guide or the Triple Combination index.

  .venv\\Scripts\\python.exe -I tool/build_entities_pack.py [--out generated-artifacts/entities-pack-v1]
"""
import argparse
import bisect
import hashlib
import json
import re
import shutil
import sqlite3
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKUP = ROOT.parent / 'scriptura' / 'app-backups' / 'scriptures_reader_mobile-before-phase0-20261011' / 'assets' / 'resources' / 'db'
TOTAL_VERSES = 41995
MIN_VERSES = {'person': 8, 'place': 5, 'group': 5}
GENERIC_SHARE = 0.05
CAPITALISED_SHARE = 0.85
KEEP_TYPES = set(MIN_VERSES)
NOT_PLACES = ('month', 'calendar', 'festival', 'feast')
PLACE_CUES = {'in', 'into', 'to', 'unto', 'from', 'at', 'of', 'land', 'city', 'cities', 'wilderness', 'mount', 'mountain', 'valley',
              'river', 'sea', 'toward', 'towards', 'near', 'through', 'out', 'over', 'borders', 'border', 'coasts', 'coast', 'plain',
              'plains', 'region', 'country', 'gate', 'against', 'beyond', 'upon'}
HARD_PLACE = {'land', 'city', 'cities', 'wilderness', 'valley', 'mount', 'mountain', 'river', 'sea', 'coasts', 'borders', 'plain',
              'plains', 'region', 'country'}
GENERIC = {'son', 'of', 'the', 'king', 'father', 'brother', 'daughter', 'wife', 'mother', 'priest', 'prophet', 'captain', 'judge',
           'servant', 'sister', 'and', 'a', 'an', 'in', 'tribe', 'tribal', 'land', 'city', 'new', 'old', 'testament', 'nephite',
           'lamanite', 'jaredite', 'people', 'house'}
VAGUE = {'the', 'king', 'queen', 'valley', 'mount', 'mountain', 'city', 'land', 'river', 'sea', 'tribe', 'high', 'lord',
         'house', 'people', 'kingdom', 'region', 'nation', 'group', 'man', 'woman', 'kingmen'}
LOWER = {'of', 'the', 'and', 'in', 'a', 'an', 'to', 'from', 'at'}
CAPS = re.compile(r'\b[A-Z][a-z]+')
SKIP_CAPS = {'Lord', 'God', 'Israel', 'Jesus', 'Christ', 'And', 'But', 'Then', 'Behold', 'Now', 'Thus', 'Holy', 'Ghost', 'Father',
             'Son', 'Jew', 'Jews'}
GENEALOGY = re.compile(r'\b(begat|son of|sons of|father of|daughter of|brother of)\b')
DOMINANCE = 3.0          # a bearer with >= 3x the tagged verses of all same-named rivals is taken as the referent
PROMINENT_PERSON = 40     # raw tagged verses; below this a person is almost always one of several same-named bearers
MAX_OTHER_NAMES = {'person': 2, 'place': 3, 'group': 3}
GENERIC_CUES = GENERIC - {'captain', 'king', 'prophet', 'priest', 'judge'}
COMMON_FIRST = {'the', 'house', 'temple', 'sea', 'wilderness'}


def other_names(t, head):
    """Capitalised names in the verse besides the entity's own (sentence-initial word excluded): lists and genealogies have
    many, and the entity's name there is the weakest evidence of identity."""
    names = CAPS.findall(t)
    first = CAPS.match(t).group(0) if CAPS.match(t) else ''
    names = [w for i, w in enumerate(names) if w not in SKIP_CAPS and not (i == 0 and w == first)]
    return {w for w in names if w.lower() != head.lower()}


def fold(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s.lower()) if unicodedata.category(c) != 'Mn')


def norm(s):
    return re.sub(r"[^a-z0-9 ]+", '', fold(s).replace('-', ' ')).strip()


def words(s):
    return set(re.findall(r"[a-z0-9']+", fold(s)))


def wordlist(s):
    return re.findall(r"[a-z0-9']+", fold(s).replace('-', ' '))


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 22), b''):
            h.update(c)
    return h.hexdigest()


def slug_qualifier(eid, head):
    """'person:nephi_son_of_lehi' + 'Nephi' -> 'son of Lehi'; no remainder -> ''."""
    slug = eid.split(':', 1)[1].split('_')
    head_words = wordlist(head)
    i = 0
    while i < len(slug) and i < len(head_words) and slug[i] == head_words[i]:
        i += 1
    if i == 0 and slug and slug[0] in head_words:
        i = 1
    rest = [w for w in slug[i:] if not w.isdigit()]
    # a qualifier that is one vague word, or only repeats the name, says nothing (audit: "the king", "Valley", "Kingmen")
    if len(rest) == 1 and (rest[0] in VAGUE or norm(rest[0]) == norm(head)):
        return ''
    return ' '.join(w if w in LOWER or w in {'son', 'father', 'brother', 'king', 'daughter', 'wife', 'mother', 'tribe'} else w.capitalize()
                    for w in rest)


def occurrences(tokens, name_words):
    n = len(name_words)
    return [i for i in range(len(tokens) - n + 1) if tokens[i:i + n] == name_words]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default=str(ROOT / 'generated-artifacts' / 'entities-pack-v1'))
    a = ap.parse_args()

    tags = sqlite3.connect(f'file:{(BACKUP / "verse-tags.db").as_posix()}?mode=ro&immutable=1', uri=True)
    text = {v: t for v, t in sqlite3.connect(f'file:{(ROOT / "generated-artifacts" / "release" / "content.db").as_posix()}?mode=ro', uri=True)
            .execute('SELECT verse_id, text FROM text_english')}
    ordered = {v: wordlist(t) for v, t in text.items()}
    cat = sqlite3.connect(f'file:{(ROOT / "generated-artifacts" / "release" / "catalog.db").as_posix()}?mode=ro', uri=True)
    chapters = cat.execute('SELECT book_id, first_verse_id FROM chapters ORDER BY first_verse_id').fetchall()
    firsts = [c[1] for c in chapters]

    def book_of(v):
        return chapters[bisect.bisect_right(firsts, v) - 1][0]
    tok = {v: set(w) | words(text[v].replace('-', '')) for v, w in ordered.items()}

    corroborating = set()
    for db in ('topical-guide.db', 'triple-index.db'):
        c = sqlite3.connect(f'file:{(BACKUP / db).as_posix()}?mode=ro&immutable=1', uri=True)
        corroborating |= {norm(r[0].split(',')[0]) for r in c.execute('SELECT name FROM topics')}

    verses = {}
    for eid, vid in tags.execute('SELECT entity_id, verse_id FROM ai_entity_verse_map'):
        verses.setdefault(eid, []).append(vid)
    raw = list(tags.execute('SELECT entity_id, name, type, qualifier, description, verse_count FROM ai_entity_profiles'))
    # the books holding at least a fifth of each entity's raw tagged verses: where that bearer lives
    home = {}
    for eid, vs in verses.items():
        counts = {}
        for v in vs:
            counts[book_of(v)] = counts.get(book_of(v), 0) + 1
        home[eid] = {b for b, c in counts.items() if c >= 0.2 * len(vs)}
    # homonym groups come from the RAW index, including entities that are dropped later
    same_kind, kinds_of, raw_n = {}, {}, {}
    for eid, name, typ, _q, _d, n in raw:
        if typ in KEEP_TYPES and n >= 3:
            key = norm(name.split(',')[0])
            same_kind.setdefault((typ, key), set()).add(eid)
            raw_n[eid] = n
            kinds_of.setdefault(key, set()).add(typ)

    stats = {t: {'raw_entities': 0, 'raw_links': 0, 'kept_entities': 0, 'kept_links': 0, 'corroborated': 0} for t in KEEP_TYPES}
    dropped = {'not_proper_noun': 0, 'too_few_grounded': 0, 'common_noun_behaviour': 0, 'not_a_place': 0, 'homonym_no_cue': 0}
    link_drops = {'homonym_guard': 0, 'cross_kind_guard': 0}
    kept = []
    for eid, name, typ, qual, desc, n in raw:
        if typ not in KEEP_TYPES:
            continue
        links = sorted(set(verses.get(eid, [])))
        stats[typ]['raw_entities'] += 1
        stats[typ]['raw_links'] += len(links)
        head = name.split(',')[0].strip()
        if not head or not head[0].isupper():
            dropped['not_proper_noun'] += 1
            continue
        if typ == 'person' and n < PROMINENT_PERSON:
            dropped['not_prominent_person'] = dropped.get('not_prominent_person', 0) + 1
            continue
        if head.split()[0].lower() in COMMON_FIRST:
            dropped['common_noun_behaviour'] += 1
            continue
        if typ == 'place' and any(w in (desc or '').lower() or w in (qual or '').lower() for w in NOT_PLACES):
            dropped['not_a_place'] += 1
            continue
        head_words = wordlist(head)
        slug_words = wordlist(eid.split(':', 1)[1].replace('_', ' '))
        spellings = [s - {'the', 'of', 'a', 'an'} for s in (set(head_words), set(slug_words)) if s]
        grounded = [v for v in links if v in tok and any(s <= tok[v] for s in spellings)]
        key = norm(head)
        # 6. homonym guard
        rivals = same_kind.get((typ, key), set()) - {eid}
        rival_n = sum(raw_n.get(x, 0) for x in rivals)
        if rivals and n < DOMINANCE * rival_n:
            # one of several comparable bearers of this name: a link must carry a word that tells this one apart
            cues = set(slug_words) - set(head_words) - GENERIC_CUES
            before = len(grounded)
            rival_books = set().union(*(home.get(x, set()) for x in rivals)) if rivals else set()
            # a verse is this bearer's when it carries a discriminating word, or sits in a book that is this bearer's
            # home and none of the rivals' (Nephi son of Lehi in 1-2 Nephi, Nephi son of Helaman in Helaman)
            grounded = [v for v in grounded
                        if (cues & tok[v]) or (book_of(v) in home.get(eid, set()) and book_of(v) not in rival_books)]
            link_drops['homonym_guard'] += before - len(grounded)
        # a person's name inside "land of X" / "city of X" is the place, whatever else the index knows
        if typ == 'person':
            before = len(grounded)
            grounded = [v for v in grounded if not (occurrences(ordered[v], head_words) and all(
                i >= 2 and ordered[v][i - 1] == 'of' and ordered[v][i - 2] in HARD_PLACE for i in occurrences(ordered[v], head_words)))]
            link_drops['person_inside_place_phrase'] = link_drops.get('person_inside_place_phrase', 0) + before - len(grounded)
        # 7. cross-kind guard
        if len(kinds_of.get(key, ())) >= 2:
            before = len(grounded)
            keep = []
            for v in grounded:
                toks = ordered[v]
                spots = occurrences(toks, head_words)
                if typ == 'place':
                    ok = any(PLACE_CUES & set(toks[max(0, i - 3):i]) for i in spots)
                else:
                    ok = not all(i >= 2 and toks[i - 1] == 'of' and toks[i - 2] in HARD_PLACE for i in spots) if spots else True
                if ok:
                    keep.append(v)
            grounded = keep
            link_drops['cross_kind_guard'] += before - len(grounded)
        before = len(grounded)
        grounded = [v for v in grounded if len(other_names(text[v], head)) <= MAX_OTHER_NAMES[typ]
                    and not (typ == 'person' and GENEALOGY.search(text[v]))]
        link_drops['list_or_genealogy'] = link_drops.get('list_or_genealogy', 0) + before - len(grounded)
        if len(grounded) < MIN_VERSES[typ]:
            dropped['too_few_grounded'] += 1
            continue
        if len(head_words) == 1:
            pat = re.compile(r'\b' + re.escape(head) + r'\b')
            caps = sum(1 for v in grounded if pat.search(text[v]))
            if caps / len(grounded) < CAPITALISED_SHARE:
                dropped['common_noun_behaviour'] += 1
                continue
        corro = norm(head) in corroborating
        kept.append([eid, head, typ, slug_qualifier(eid, head), '', len(grounded), 0, int(corro), grounded])
        stats[typ]['kept_entities'] += 1
        stats[typ]['kept_links'] += len(grounded)
        stats[typ]['corroborated'] += int(corro)

    # 9. merge duplicate places/groups (same name, same or no qualifier): the tagger split them by chapter
    kept.sort(key=lambda e: (-e[5], e[0]))
    canon, merged = [], 0
    for e in kept:
        if e[2] != 'person':
            for c in canon:
                if c[2] == e[2] and norm(c[1]) == norm(e[1]) and (c[3] == e[3] or not c[3] or not e[3]):
                    c[8] = sorted(set(c[8]) | set(e[8]))
                    c[3] = c[3] or e[3]
                    c.append(e[0])
                    merged += 1
                    break
            else:
                canon.append(e + [])
        else:
            canon.append(e + [])
    aliases, final = [], []
    overrides = json.loads((ROOT / 'tool' / 'data' / 'entity_overrides.json').read_text('utf-8'))
    overridden = 0
    for e in canon:
        extra = e[9:]
        e = e[:9]
        o = overrides.get(e[0], {})
        if o.get('drop'):
            overridden += 1
            continue
        if 'qualifier' in o:
            e[3] = o['qualifier']
            overridden += 1
        if 'name' in o:
            e[1] = o['name']
        e[5] = len(e[8])
        e[6] = int(e[5] > GENERIC_SHARE * TOTAL_VERSES)
        final.append(e)
        aliases += [(x, e[0]) for x in extra]
    stats['merged_duplicates'] = merged
    stats['overridden'] = overridden
    stats['link_drops'] = link_drops
    for t in KEEP_TYPES:
        stats[t]['kept_entities'] = sum(1 for e in final if e[2] == t)
        stats[t]['kept_links'] = sum(len(e[8]) for e in final if e[2] == t)

    out = Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    db = out / 'entities.db'
    c = sqlite3.connect(db)
    c.executescript("""
        PRAGMA journal_mode=OFF;
        CREATE TABLE people(entity_id TEXT PRIMARY KEY, name TEXT NOT NULL, qualifier TEXT NOT NULL, description TEXT NOT NULL,
                            verse_count INTEGER NOT NULL, generic INTEGER NOT NULL, corroborated INTEGER NOT NULL) WITHOUT ROWID;
        CREATE TABLE person_verses(entity_id TEXT NOT NULL, verse_id INTEGER NOT NULL, PRIMARY KEY(entity_id, verse_id)) WITHOUT ROWID;
        CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
        CREATE TABLE aliases(alias_id TEXT PRIMARY KEY, entity_id TEXT NOT NULL) WITHOUT ROWID;
    """)
    final.sort()
    c.executemany('INSERT INTO aliases VALUES (?,?)', aliases)
    c.executemany('INSERT INTO people VALUES (?,?,?,?,?,?,?)', [(e[0], e[1], e[3], e[4], e[5], e[6], e[7]) for e in final])
    c.executemany('INSERT INTO person_verses VALUES (?,?)', [(e[0], v) for e in final for v in e[8]])
    c.executemany('INSERT INTO meta VALUES (?,?)', [
        ('source', 'legacy AI entity index, purified (grounded, homonym- and cross-kind-guarded; qualifiers from id slugs)'),
        ('min_verses', json.dumps(MIN_VERSES)), ('capitalised_share', str(CAPITALISED_SHARE)), ('generic_share', str(GENERIC_SHARE))])
    c.commit()
    c.execute('VACUUM')
    c.close()
    manifest = {'license': {'spdx': 'MIT', 'holder': 'Scriptura Labs', 'note': 'names of people, places and groups with verse ids; machine-generated; may contain errors; no scripture text'}, 'format': 'entities-pack-v1', 'files': {'entities.db': {'bytes': db.stat().st_size, 'sha256': sha256(db)}},
                'stats': stats, 'dropped': dropped}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=1), 'utf-8')
    qdir = ROOT / 'local-benchmarks'
    qdir.mkdir(exist_ok=True)
    (qdir / 'entities_quality.json').write_text(json.dumps({'stats': stats, 'dropped': dropped}, indent=1), 'utf-8')
    print(json.dumps({'stats': stats, 'dropped': dropped}, indent=1))
    print(f'entities pack: {db.stat().st_size / 1e6:.2f} MB at {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
