"""Build topics-pack-v1: verse <-> topic membership with tf-idf weights, for the similar-verses topic lane.

Source: the Topical Guide's verse-to-topic map (legacy topical-guide.db in the phase-0 backup). The pack carries topic
numbers and weights only: no topic names, no snippets, no text. It is rights-gated (DATA_SOURCES_PLAN D9) and is not
listed in the bucket index unless tool/make_bucket_index.py is run with --include-topics.

Weights: idf(t) = ln((N + 1) / (df(t) + 1)) + 1 over the N verses; each verse's vector is L2-normalised so the dot
product of two verses is their cosine. Evaluated with human judgments in tool/topic_review_sheet.py (nDCG@8 0.686 ->
0.798 at topic weight 0.5).

  .venv\\Scripts\\python.exe -I tool/build_topics_pack.py [--out generated-artifacts/topics-pack-v1]
"""
import argparse
import hashlib
import json
import math
import shutil
import sqlite3
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
BACKUP = ROOT.parent / 'scriptura' / 'app-backups' / 'scriptures_reader_mobile-before-phase0-20261011' / 'assets' / 'resources' / 'db'
WEIGHT = 0.5      # topic weight in the fusion (genome weight 1.0)
LANE_K = 200      # candidates taken from each lane


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 22), b''):
            h.update(c)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default=str(ROOT / 'generated-artifacts' / 'topics-pack-v1'))
    a = ap.parse_args()
    verse_ids = set(int(v) for v in np.load(ROOT / 'generated-artifacts' / 'engine-pack' / 'retrieval' / 'verse_ids.npy'))
    n = len(verse_ids)
    c = sqlite3.connect(f'file:{(BACKUP / "topical-guide.db").as_posix()}?mode=ro&immutable=1', uri=True)
    pairs = sorted({(slug, v) for slug, v in c.execute('SELECT topic_slug, verse_id FROM topic_verse_index') if v in verse_ids})
    topics = {}
    for slug, _ in pairs:
        topics.setdefault(slug, len(topics))
    df = {}
    by_verse = {}
    for slug, v in pairs:
        t = topics[slug]
        df[t] = df.get(t, 0) + 1
        by_verse.setdefault(v, []).append(t)
    idf = {t: math.log((n + 1) / (d + 1)) + 1 for t, d in df.items()}
    rows = []
    for v, ts in by_verse.items():
        norm = math.sqrt(sum(idf[t] ** 2 for t in ts))
        rows += [(t, v, idf[t] / norm) for t in ts]
    rows.sort()

    out = Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    db = out / 'topics.db'
    d = sqlite3.connect(db)
    d.executescript("""
        PRAGMA journal_mode=OFF;
        CREATE TABLE posting(topic INTEGER NOT NULL, verse_id INTEGER NOT NULL, w REAL NOT NULL, PRIMARY KEY(topic, verse_id)) WITHOUT ROWID;
        CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
    """)
    d.executemany('INSERT INTO posting VALUES (?,?,?)', rows)
    d.executemany('INSERT INTO meta VALUES (?,?)', [
        ('source', 'Topical Guide verse-to-topic map (topic numbers and weights only)'), ('weight', str(WEIGHT)),
        ('lane_k', str(LANE_K)), ('idf', 'ln((N+1)/(df+1))+1'), ('verses', str(len(by_verse))), ('topics', str(len(topics)))])
    d.commit()
    d.execute('VACUUM')
    d.close()
    manifest = {'license': {'spdx': None, 'holder': 'Scriptura Labs', 'note': 'topic numbers and weights only; rights-gated, not licensed for redistribution'}, 'format': 'topics-pack-v1', 'weight': WEIGHT, 'lane_k': LANE_K,
                'files': {'topics.db': {'bytes': db.stat().st_size, 'sha256': sha256(db)}},
                'stats': {'verses': len(by_verse), 'topics': len(topics), 'postings': len(rows), 'verse_universe': n}}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=1), 'utf-8')
    print(json.dumps(manifest['stats']), f'-> {db.stat().st_size / 1e6:.2f} MB at {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
