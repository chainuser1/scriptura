"""Build answers-pack-v1: "what this passage speaks to", from the question genome.

Source: questions_genome.db (47,400 study questions mapped to verses, in the shared 568-d genome space) and
scriptures_genome.db (verse vectors). Only questions that read as natural, self-contained questions are kept, in the
languages whose translation is clean. For each verse the pack lists up to TOP_K questions:

  * explicit targets of the question set (curated edges), then
  * nearest questions by cosine in genome space, kept only above a floor calibrated on the explicit edges.

Quality is measured, not asserted, in local-benchmarks/answers_quality.json: for the explicit edges, how often the
true question is among a verse's top-5 neighbours (hit@5, MRR), and the cosine floor used.

  .venv\\Scripts\\python.exe -I tool/build_answers_pack.py [--out generated-artifacts/answers-pack-v1]
"""
import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
APPDB = ROOT.parent / 'scriptura' / 'application_databases'
LANGS = ['english', 'spanish', 'tagalog', 'cebuano', 'greek']
TOP_K = 5
KINDS_OK = {'doctrine', 'pastoral', 'practice', 'soul', 'knowledge'}
START = re.compile(r"(?i)^(what|who|why|how|where|when|which|is|are|can|does|do|did|should|will|may|must|in what|to whom|by what)\b")
BAD_CHARS = re.compile(r'[⁇�]')


def natural_en(t):
    t = t.strip()
    return (t.endswith('?') and ';' not in t and 15 <= len(t) <= 150 and not BAD_CHARS.search(t) and bool(START.match(t)))


def clean_tr(t):
    t = (t or '').strip()
    body = t[:-1] if t[-1:] in '?;？' else t
    return bool(t) and len(t) <= 220 and ';' not in body and not BAD_CHARS.search(t) and t[-1] in '?;？'


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 22), b''):
            h.update(c)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default=str(ROOT / 'generated-artifacts' / 'answers-pack-v1'))
    ap.add_argument('--min-weight', type=float, default=0.4,
                    help='curated edges below this weight are collection-level and weakly tied to the verse (default 0.4)')
    ap.add_argument('--min-cosine', type=float, default=0.88,
                    help='and the question must sit this close to the verse in genome space (default 0.88)')
    ap.add_argument('--near', action='store_true',
                    help='also include nearest-neighbour questions (about 7 in 10 read as relevant; off by default)')
    ap.add_argument('--floor-percentile', type=float, default=50.0,
                    help='nearest-neighbour questions are kept only above this percentile of the curated-edge cosine')
    a = ap.parse_args()
    q = sqlite3.connect(f'file:{(APPDB / "questions_genome.db").as_posix()}?mode=ro', uri=True)
    g = sqlite3.connect(f'file:{(APPDB / "scriptures_genome.db").as_posix()}?mode=ro', uri=True)

    kinds = dict(q.execute('SELECT q_id, kind FROM question_metadata'))
    keep = {qid: t.strip() for qid, t in q.execute('SELECT q_id, question FROM questions_english')
            if natural_en(t) and kinds.get(qid) in KINDS_OK}
    print(f'{len(keep)} natural questions kept of 47,400')

    texts = {'english': keep}
    for lang in LANGS[1:]:
        rows = {qid: t.strip() for qid, t in q.execute(f'SELECT q_id, question FROM questions_{lang}') if qid in keep and clean_tr(t)}
        texts[lang] = rows
        print(f'  {lang}: {len(rows)} clean translations')

    qids = sorted(keep)
    qi = {x: i for i, x in enumerate(qids)}
    Q = np.frombuffer(b''.join(r[0] for r in q.execute('SELECT vector FROM question_vectors ORDER BY q_id')), dtype='<f4')
    all_q = [r[0] for r in q.execute('SELECT q_id FROM question_vectors ORDER BY q_id')]
    Q = Q.reshape(len(all_q), -1)
    pos = {x: i for i, x in enumerate(all_q)}
    Q = Q[[pos[x] for x in qids]]
    Q /= np.linalg.norm(Q, axis=1, keepdims=True).clip(1e-9)
    vids = [r[0] for r in g.execute('SELECT verse_id FROM scripture_vectors ORDER BY verse_id')]
    V = np.frombuffer(b''.join(r[0] for r in g.execute('SELECT vector FROM scripture_vectors ORDER BY verse_id')), dtype='<f4').reshape(len(vids), -1).copy()
    V /= np.linalg.norm(V, axis=1, keepdims=True).clip(1e-9)
    vi = {v: i for i, v in enumerate(vids)}

    explicit = {}
    for qid, vid, w in q.execute('SELECT q_id, verse_id, weight FROM question_targets'):
        if qid in qi and vid in vi:
            explicit.setdefault(vid, {})[qid] = w

    # verse -> question similarities (41,995 x ~9.8k floats = fine in blocks)
    top_idx = np.zeros((len(vids), 12), dtype=np.int32)
    top_cos = np.zeros((len(vids), 12), dtype=np.float32)
    for s in range(0, len(vids), 2048):
        S = V[s:s + 2048] @ Q.T
        idx = np.argpartition(-S, 12, axis=1)[:, :12]
        c = np.take_along_axis(S, idx, axis=1)
        o = np.argsort(-c, axis=1)
        top_idx[s:s + 2048] = np.take_along_axis(idx, o, axis=1)
        top_cos[s:s + 2048] = np.take_along_axis(c, o, axis=1)

    # calibrate the floor on the curated edges: the cosine of explicit (verse, question) pairs
    edge_cos, ranks = [], []
    for vid, qs in explicit.items():
        row = V[vi[vid]]
        sims = Q @ row
        order = np.argsort(-sims)
        rank_of = np.empty(len(qids), dtype=np.int32)
        rank_of[order] = np.arange(len(qids))
        for qid in qs:
            edge_cos.append(float(sims[qi[qid]]))
            ranks.append(int(rank_of[qi[qid]]) + 1)
    edge_cos = np.array(edge_cos)
    ranks = np.array(ranks)
    floor = float(np.percentile(edge_cos, a.floor_percentile))
    quality = {
        'questions': len(keep), 'explicit_edges': int(len(ranks)), 'verses_with_explicit': len(explicit),
        'verse_to_question_hit@1': float((ranks <= 1).mean()), 'hit@5': float((ranks <= 5).mean()), 'hit@10': float((ranks <= 10).mean()),
        'mrr': float((1.0 / ranks).mean()), 'floor_percentile': a.floor_percentile, 'cosine_floor': floor,
        'explicit_cosine_p50': float(np.percentile(edge_cos, 50)),
    }

    rows = []  # (verse_id, q_id, rank, score, explicit)
    for vid in vids:
        picked, seen = [], set()
        for qid, w in sorted(explicit.get(vid, {}).items(), key=lambda kv: -kv[1]):
            cosine = float(V[vi[vid]] @ Q[qi[qid]])
            if w < a.min_weight or cosine < a.min_cosine:
                continue
            picked.append((qid, cosine, 1))
            seen.add(qid)
        for j in range(12 if a.near else 0):
            if len(picked) >= TOP_K:
                break
            qid = qids[top_idx[vi[vid], j]]
            if qid in seen or top_cos[vi[vid], j] < floor:
                continue
            seen.add(qid)
            picked.append((qid, float(top_cos[vi[vid], j]), 0))
        picked.sort(key=lambda x: (-x[2], -x[1]))
        for r, (qid, sc, ex) in enumerate(picked[:TOP_K]):
            rows.append((vid, qid, r, round(sc, 4), ex))
    covered = len({r[0] for r in rows})
    quality.update({'verses_covered': covered, 'verse_question_rows': len(rows), 'share_explicit': float(np.mean([r[4] for r in rows]))})

    out = Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    db = out / 'answers.db'
    c = sqlite3.connect(db)
    c.executescript("""
        PRAGMA journal_mode=OFF;
        CREATE TABLE question(q_id TEXT PRIMARY KEY, kind TEXT NOT NULL) WITHOUT ROWID;
        CREATE TABLE question_text(q_id TEXT NOT NULL, language TEXT NOT NULL, text TEXT NOT NULL, PRIMARY KEY(q_id, language)) WITHOUT ROWID;
        CREATE TABLE verse_question(verse_id INTEGER NOT NULL, q_id TEXT NOT NULL, rank INTEGER NOT NULL, score REAL NOT NULL,
                                    explicit INTEGER NOT NULL, PRIMARY KEY(verse_id, rank)) WITHOUT ROWID;
        CREATE INDEX verse_question_q ON verse_question(q_id);
        CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
    """)
    used = {r[1] for r in rows}
    c.executemany('INSERT INTO question VALUES (?,?)', [(x, kinds[x]) for x in sorted(used)])
    for lang, tx in texts.items():
        c.executemany('INSERT INTO question_text VALUES (?,?,?)', [(x, lang, tx[x]) for x in sorted(used) if x in tx])
    c.executemany('INSERT INTO verse_question VALUES (?,?,?,?,?)', rows)
    c.executemany('INSERT INTO meta VALUES (?,?)', [
        ('source', 'questions_genome.db + scriptures_genome.db (project-generated; machine-generated questions)'),
        ('cosine_floor', f'{floor:.4f}'), ('top_k', str(TOP_K))])
    c.commit()
    c.execute('VACUUM')
    c.close()

    files = {'answers.db': {'bytes': db.stat().st_size, 'sha256': sha256(db)}}
    (out / 'manifest.json').write_text(json.dumps({'license': {'spdx': 'MIT', 'holder': 'Scriptura Labs', 'note': 'study questions mapped to verses; machine-generated; may contain errors; no scripture text'}, 'format': 'answers-pack-v1', 'files': files, 'quality': quality}, indent=1), 'utf-8')
    qdir = ROOT / 'local-benchmarks'
    qdir.mkdir(exist_ok=True)
    (qdir / 'answers_quality.json').write_text(json.dumps(quality, indent=1), 'utf-8')
    print(json.dumps(quality, indent=1))
    print(f'answers pack: {db.stat().st_size / 1e6:.1f} MB at {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
