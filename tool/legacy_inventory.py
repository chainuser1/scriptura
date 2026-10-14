"""Classify and hash every legacy resource file. Refuses to write if any file is unclassified.

  .venv\\Scripts\\python.exe -I tool/legacy_inventory.py [--root PATH] [--out docs/legacy_disposition.json]
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQ, OPT, ARCH, DISC = 'required_pack', 'optional_pack', 'archive', 'discard'

# key: path relative to the resources root, or bare file name -> (class, pack, reason)
RULES = {
    'lds-scriptures-sqlite.db': (REQ, 'edition-kjv-lds', 'Default English display edition (owner decision D1); full KJV/LDS text, same IDs'),
    'user-data.db': (ARCH, None, 'Old adaptive-search learning state; contains no notes, bookmarks or highlights'),
    'nrsvue-scriptures-sqlite.db': (ARCH, None, 'NRSVue; already the base English source for 27,567 verses'),
    'ylt-scriptures-sqlite.db': (OPT, 'edition-ylt', "Young's Literal Translation, full"),
    'rotherham-scriptures-sqlite.db': (OPT, 'edition-rotherham', 'Rotherham, full'),
    'cebuano-scriptures-sqlite.db': (ARCH, None, 'Already represented in scriptures_genome.db'),
    'greek-scriptures-sqlite.db': (ARCH, None, 'Already represented in scriptures_genome.db (text identical)'),
    'spanish-scriptures-sqlite.db': (ARCH, None, 'Already represented in scriptures_genome.db'),
    'tagalog-scriptures-sqlite.db': (ARCH, None, 'Already represented in scriptures_genome.db'),
    'ilocano-scriptures-sqlite.db': (ARCH, None, 'Not served: the encoder and genome head were not trained on this language (owner decision D7, 2026-10-13)'),
    'waray-scriptures-sqlite.db': (ARCH, None, 'Not served: the encoder and genome head were not trained on this language (owner decision D7, 2026-10-13)'),
    'japanese-scriptures-sqlite.db': (DISC, None, 'Excluded by owner decision D6 (2026-10-13)'),
    'topical-guide.db': (OPT, 'study-aids-topics', 'Topical Guide index; drop topic_ppr/verse_pagerank (old graph); rights unreviewed'),
    'triple-index.db': (OPT, 'study-aids-index', 'Triple Combination index; rights unreviewed'),
    'verse-cross-refs.db': (OPT, 'study-aids-crossrefs', 'Cross-references with snippets; provenance unreviewed'),
    'footnotes-lds-summaries.db': (OPT, 'study-aids-footnotes', 'Chapter summaries and notes; per-column rights unreviewed'),
    'chapter-summaries-fts.db': (OPT, 'ai-summaries', 'AI-generated (kimi-k2); must be labeled AI-generated'),
    'verse-summaries.db': (OPT, 'ai-summaries', 'AI-generated (kimi-k2); must be labeled AI-generated'),
    'verse-tags.db': (OPT, 'entities', 'AI people/places/doctrine tags; quality unreviewed'),
    'verse-embeddings.db': (DISC, None, 'Legacy 768-d embeddings + HNSW; superseded (PLAN 1.8)'),
    'verse_embeddings.db': (DISC, None, 'Empty legacy file'),
    'verse-graph.db': (DISC, None, 'Legacy kNN/clusters/spectral; superseded (PLAN 1.8)'),
    'search-graph.db': (DISC, None, 'Legacy PageRank/PMI/entity graph; superseded (PLAN 1.8)'),
    'concept-embeddings.db': (DISC, None, 'Legacy concept embeddings for query expansion; superseded (PLAN 1.8)'),
    'models/scripture-bge/onnx/model_quantized.onnx': (DISC, None, 'Legacy encoder, hashed-word tokenizer; never a substitute (PLAN 2, 3)'),
    'models/scripture-bge/onnx/tokenizer.json': (DISC, None, 'Legacy tokenizer; the pinned BGE-M3 tokenizer is authoritative'),
}


def classify(rel):
    for suffix in ('-wal', '-shm'):
        if rel.endswith(suffix):
            c, pack, _ = classify(rel[: -len(suffix)])
            return c, pack, f'SQLite {suffix[1:]} sidecar of {rel[: -len(suffix)].rsplit("/", 1)[-1]}'
    if rel in RULES:
        return RULES[rel]
    if rel.startswith('db/') and rel[3:] in RULES:
        return RULES[rel[3:]]
    raise KeyError(rel)


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 22), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    default_root = ROOT / 'assets' / 'resources'
    if not default_root.exists():
        default_root = ROOT / 'legacy-quarantine' / 'resources'
    ap.add_argument('--root', default=str(default_root))
    ap.add_argument('--out', default=str(ROOT / 'docs' / 'legacy_disposition.json'))
    a = ap.parse_args()
    root = Path(a.root)
    entries, unknown = [], []
    for p in sorted(x for x in root.rglob('*') if x.is_file()):
        rel = p.relative_to(root).as_posix()
        try:
            cls, pack, reason = classify(rel)
        except KeyError:
            unknown.append(rel)
            continue
        entries.append({'path': rel, 'bytes': p.stat().st_size, 'sha256': sha256(p), 'class': cls, 'pack': pack, 'reason': reason})
    if unknown:
        print('UNCLASSIFIED files (add a rule in RULES):', *unknown, sep='\n  ')
        return 1
    Path(a.out).write_text(json.dumps({'root': 'assets/resources', 'files': entries}, indent=1), 'utf-8')
    by = {}
    for e in entries:
        by[e['class']] = by.get(e['class'], 0) + 1
    print(f'{len(entries)} files classified: {by} -> {a.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
