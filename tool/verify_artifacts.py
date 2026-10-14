"""Verify the imported Scripture Genome artifacts (PLAN Phase 1, handoff section 4).

Read-only. Run:  python -I tool/verify_artifacts.py [IMPORT_DIR] [--full]
IMPORT_DIR defaults to .artifact-staging/import-application-v1 (databases/ + extracted/).
--full runs SQLite integrity_check (slow on the 860 MB raw DB) and parses every raw genome row.
Exit code 0 only if every hard check passes. Order-hash reproduction is informational.
"""
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

GENE_SHA = '16878f92a2f6434b39ef6d68c633f2cd815751f2b4be8767a309e32442baf195'
CKPT_SHA = '5a68ef73167f48899c927dfb5e25dfe8ff50d0b8e8310cd6f3ff3c93b8bf9952'
BASE_REV = '5617a9f61b028005a4858fdac845db406aefb181'
N_VERSES, N_QUESTIONS, N_GENES, DENSE_DIM, VOCAB, NNZ = 41995, 47400, 568, 1024, 250002, 1156270

failures = []


def check(ok, label, detail=''):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f'  [{detail}]' if detail else ''))
    if not ok:
        failures.append(label)


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 22), b''):
            h.update(chunk)
    return h.hexdigest()


def db(path):
    return sqlite3.connect(f'file:{Path(path).as_posix()}?mode=ro', uri=True)


def vectors(conn, table, key):
    """-> (ids, float32 [n,568]); validates blob length/endianness by construction."""
    ids, blobs = [], []
    for k, b in conn.execute(f'SELECT {key}, vector FROM {table} ORDER BY {key}'):
        ids.append(k)
        blobs.append(b)
    assert all(len(b) == N_GENES * 4 for b in blobs), f'{table}: bad blob length'
    return ids, np.frombuffer(b''.join(blobs), dtype='<f4').reshape(-1, N_GENES)


def sane(m):
    return bool(np.isfinite(m).all() and m.min() >= 0 and m.max() <= 1)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    full = '--full' in sys.argv
    root = Path(args[0]) if args else Path(__file__).resolve().parent.parent / '.artifact-staging' / 'import-application-v1'
    ext, dbs = root / 'extracted', root / 'databases'

    print('== inner manifests')
    for d in sorted(p for p in ext.iterdir() if p.is_dir()):
        m = json.loads((d / 'manifest.json').read_text('utf-8'))
        on_disk = {p.relative_to(d).as_posix() for p in d.rglob('*') if p.is_file()} - {'manifest.json'}
        check(on_disk == set(m['files']), f'{d.name}: file set equals manifest')
        for name, e in m['files'].items():
            p = d / name
            check(p.is_file() and p.stat().st_size == e['bytes'] and sha256(p) == e['sha256'], f'{d.name}/{name}')

    print('== pinned identities')
    base = json.loads((ext / 'bge-m3-pinned' / 'manifest.json').read_text('utf-8'))
    check(base['revision'] == BASE_REV, 'base revision pinned')
    genes = {d.name: sha256(d / 'gene_ids.txt') for d in ext.iterdir() if (d / 'gene_ids.txt').exists()}
    check(set(genes.values()) == {GENE_SHA}, 'gene_ids.txt identical and pinned', f'{len(genes)} copies')
    check(sha256(ext / 'scripture-genome-question-hidden4096-full' / 'best.pt') == CKPT_SHA, 'head checkpoint pinned')
    gene_ids = (ext / 'scripture-retrieval-english-v1' / 'gene_ids.txt').read_text('utf-8').split('\n')
    gene_ids = [g for g in gene_ids if g]
    check(len(gene_ids) == N_GENES and len(set(gene_ids)) == N_GENES, 'gene ids: 568 unique')

    print('== application database files vs db manifest')
    dm = json.loads((dbs / 'manifest.json').read_text('utf-8'))
    for name, e in dm['files'].items():
        p = dbs / name
        check(p.stat().st_size == e['bytes'] and sha256(p) == e['sha256'], f'databases/{name}')

    print('== retrieval arrays')
    r = ext / 'scripture-retrieval-english-v1'
    verse_ids = np.load(r / 'verse_ids.npy', allow_pickle=False)
    dense = np.load(r / 'dense_embeddings.f16.npy', allow_pickle=False)
    genome = np.load(r / 'genome_vectors.f16.npy', allow_pickle=False)
    weighted = np.load(r / 'weighted_genome_embeddings.f16.npy', allow_pickle=False)
    check(verse_ids.shape == (N_VERSES,) and len(set(verse_ids.tolist())) == N_VERSES, 'verse_ids: 41,995 unique')
    check(dense.shape == (N_VERSES, DENSE_DIM) and dense.dtype == np.float16 and np.isfinite(dense).all(), 'dense [41995,1024] f16 finite')
    norms = np.linalg.norm(dense.astype(np.float32), axis=1)
    check(abs(norms.min() - 1) < 5e-3 and abs(norms.max() - 1) < 5e-3, 'dense rows L2-normalized', f'norm {norms.min():.4f}..{norms.max():.4f}')
    check(genome.shape == (N_VERSES, N_GENES) and sane(genome.astype(np.float32)), 'genome [41995,568] f16 finite in [0,1]')
    check(weighted.shape == (N_VERSES, N_GENES) and np.isfinite(weighted).all(), 'weighted genome [41995,568] finite')
    with np.load(r / 'sparse_index.csr.npz', allow_pickle=False) as z:
        indptr, indices, data, shape = z['indptr'], z['indices'], z['data'], tuple(z['shape'])
    check(shape == (N_VERSES, VOCAB) and len(data) == NNZ and indptr[0] == 0 and indptr[-1] == NNZ and (np.diff(indptr) >= 0).all()
          and indices.min() >= 0 and indices.max() < VOCAB and np.isfinite(data).all() and (data > 0).all(), 'sparse CSR structure',
          f'shape={shape} nnz={len(data)}')
    rows = [json.loads(l) for l in (r / 'scripture_text.jsonl').read_text('utf-8').splitlines()]
    check([x['verse_id'] for x in rows] == verse_ids.tolist(), 'scripture_text.jsonl order == verse_ids.npy')

    cfg = json.loads((r / 'retrieval_config.json').read_text('utf-8'))
    vid = verse_ids.astype('<i8')
    candidates = {
        'int64 LE bytes': vid.tobytes(),
        'newline-joined': '\n'.join(map(str, verse_ids.tolist())).encode(),
        'comma-joined': ','.join(map(str, verse_ids.tolist())).encode(),
        'json compact': json.dumps(verse_ids.tolist(), separators=(',', ':')).encode(),
        'json default': json.dumps(verse_ids.tolist()).encode(),
    }
    hit = [k for k, v in candidates.items() if hashlib.sha256(v).hexdigest() == cfg['verse_order_sha256']]
    print(f"INFO  verse_order_sha256 reproduced by: {hit or 'none of the tried serializations'}")

    print('== scriptures_genome.db')
    c = db(dbs / 'scriptures_genome.db')
    check(c.execute('PRAGMA ' + ('integrity_check' if full else 'quick_check')).fetchone()[0] == 'ok', 'sqlite integrity')
    check(c.execute('PRAGMA foreign_key_check').fetchall() == [], 'foreign_key_check clean')
    ids, sv = vectors(c, 'scripture_vectors', 'verse_id')
    check(len(ids) == N_VERSES and sane(sv), 'scripture_vectors: 41,995 finite float32 LE in [0,1]')
    check(set(ids) == set(verse_ids.tolist()), 'scripture_vectors ids == verse_ids.npy')
    err =np.abs(sv[np.searchsorted(ids, verse_ids)] - genome.astype(np.float32)).max()
    check(err < 2e-3, 'DB vectors match genome_vectors.f16.npy by verse ID', f'max abs diff {err:.2e}')
    en = dict(c.execute('SELECT verse_id, scripture_text FROM scriptures_english'))
    check(set(en) == set(ids), 'scriptures_english covers every verse ID')
    diff = sum(1 for x in rows if en.get(x['verse_id']) != x['scripture_text'])
    print(f'INFO  display-vs-retrieval English text differs for {diff} of {len(rows)} verses (needs explicit edition policy if >0)')
    cov = c.execute('SELECT language, table_name, rows, expected_rows, complete FROM language_coverage').fetchall()
    for lang, table, n, exp, comp in cov:
        actual = c.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
        check(actual == n and (n == exp) == bool(comp), f'coverage {lang}', f'{n}/{exp}')
    meta = dict(c.execute('SELECT key, value FROM database_metadata'))
    cand = {k: hashlib.sha256(v).hexdigest() for k, v in {
        'newline-joined': '\n'.join(gene_ids).encode(), 'newline+trailing': ('\n'.join(gene_ids) + '\n').encode(),
        'json compact': json.dumps(gene_ids, separators=(',', ':')).encode(), 'json default': json.dumps(gene_ids).encode(),
    }.items()}
    print(f"INFO  gene_order_hash {meta['gene_order_hash'][:12]}.. reproduced by: "
          f"{[k for k, v in cand.items() if v == meta['gene_order_hash']] or 'none of the tried serializations'}")
    check(meta.get('dimensions') == '568' and meta.get('vector_encoding') == 'float32_little_endian', 'metadata dims/encoding')

    print('== questions_genome.db')
    q = db(dbs / 'questions_genome.db')
    check(q.execute('PRAGMA ' + ('integrity_check' if full else 'quick_check')).fetchone()[0] == 'ok', 'sqlite integrity')
    check(q.execute('PRAGMA foreign_key_check').fetchall() == [], 'foreign_key_check clean')
    qids, qv = vectors(q, 'question_vectors', 'q_id')
    check(len(qids) == N_QUESTIONS and sane(qv), 'question_vectors: 47,400 finite float32 LE in [0,1]')
    vset = set(ids)
    tg = q.execute('SELECT q_id, verse_id, weight FROM question_targets').fetchall()
    check(len(tg) == dm['build']['questions']['target_edges'], 'question_targets edge count', str(len(tg)))
    missing = [t for t in tg if t[1] not in vset]
    check(not missing, 'every question target verse_id exists in scriptures_genome.db', f'{len(missing)} dangling')
    check(all(0 < t[2] <= 1 for t in tg) and {t[0] for t in tg} <= set(qids), 'target weights in (0,1] and q_ids exist')
    check(q.execute('SELECT count(*) FROM questions_english').fetchone()[0] == N_QUESTIONS, 'questions_english: 47,400')

    print('== scripture_genome_raw.db')
    w = db(dbs / 'scripture_genome_raw.db')
    check(w.execute('PRAGMA ' + ('integrity_check' if full else 'quick_check')).fetchone()[0] == 'ok', 'sqlite integrity')
    rid = [x[0] for x in w.execute('SELECT verse_id FROM verse_genome_raw ORDER BY verse_id')]
    check(rid == ids, 'raw verse ids == scripture ids')
    gset, bad, n = set(gene_ids), 0, 0
    step = 1 if full else 20
    for (j,) in w.execute('SELECT genome_raw_json FROM verse_genome_raw WHERE verse_id % ? = 0' if step > 1 else 'SELECT genome_raw_json FROM verse_genome_raw', (step,) if step > 1 else ()):
        n += 1
        bad += set(json.loads(j)) != gset
    check(bad == 0, f'raw genome JSON keys == gene ids ({n} rows checked)', f'{bad} mismatches')

    print('== head weights')
    with np.load(ext / 'scripture-genome-question-hidden4096-full' / 'head_fp32.npz', allow_pickle=False) as z:
        shapes = {k: z[k].shape for k in z.files}
        finite = all(np.isfinite(z[k]).all() for k in z.files)
    check(shapes == {'0.weight': (4096, 1024), '0.bias': (4096,), '2.weight': (568, 4096), '2.bias': (568,)} and finite, 'head_fp32 shapes finite')

    print(f"\n{'ALL HARD CHECKS PASSED' if not failures else str(len(failures)) + ' FAILED: ' + '; '.join(failures)}")
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
