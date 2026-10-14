"""Configuration identity and cache keys (PLAN 10 and 11, ENGINE_PLAN C7).

`configuration_id` is the SHA-256 of a canonical JSON of everything that can change a ranking. Two requests may share
a cache entry only if their keys are equal. Display language and edition are deliberately NOT part of the identity
(the engine returns verse IDs only; text is re-rendered from the repository).

  .venv\\Scripts\\python.exe -I tool/config_identity.py          # prints the identity of the current local artifacts
"""
import hashlib
import json
import sys
import unicodedata
from pathlib import Path

SCHEMA = 1
ROOT = Path(__file__).resolve().parent.parent
FUSION = {'weights': {'dense': 0.28, 'sparse': 0.14, 'colbert': 0.28, 'genome': 0.30},
          'family_weights': {'B': 0.75, 'I': 0.50, 'N': 0.50, 'Q': 0.0, 'T': 0.75, 'U': 0.75, 'default': 1.0},
          'lane_k': 200, 'zscore_ddof': 1, 'tie_break': 'ascending_verse_id'}


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def sha256_text(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def filter_hash(allowed_verse_ids):
    """None = whole corpus; otherwise order- and duplicate-independent."""
    if allowed_verse_ids is None:
        return None
    ids = sorted({int(v) for v in allowed_verse_ids})
    return sha256_text(','.join(map(str, ids)))


def configuration_id(parts, mode='semantic'):
    body = {'schema': SCHEMA, 'mode': mode, **parts}
    return sha256_text(canonical(body))


def cache_key(query, config_id, mode='semantic', filter_sha=None, top_k=20, search_language='english'):
    """Exact query (NFC only), plus everything that selects the ranking and its size."""
    q = unicodedata.normalize('NFC', query)
    return sha256_text(canonical({'q': q, 'config': config_id, 'mode': mode, 'filter': filter_sha,
                                  'top_k': top_k, 'search_language': search_language}))


def _sha_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 22), b''):
            h.update(chunk)
    return h.hexdigest()


def identity_from_artifacts(encoder_graph, pack_manifest, bundle, base_dir, head_npz, tokenizer_json):
    """Collect the real identities from files. Large `.data` files are hashed by their manifest entries where possible."""
    pack = json.loads(Path(pack_manifest).read_text('utf-8'))
    base = json.loads((Path(base_dir) / 'manifest.json').read_text('utf-8'))
    bundle = Path(bundle)
    data = Path(str(encoder_graph) + '.data')
    return {
        'base_model_revision': base['revision'],
        'tokenizer_sha256': _sha_file(tokenizer_json),
        'encoder': {'graph_sha256': _sha_file(encoder_graph), 'data_sha256': _sha_file(data) if data.exists() else None,
                    'name': Path(encoder_graph).name},
        'head_sha256': _sha_file(head_npz),
        'index': {
            'dense_sha256': _sha_file(bundle / 'dense_embeddings.f16.npy'),
            'genome_sha256': _sha_file(bundle / 'weighted_genome_embeddings.f16.npy'),
            'sparse_sha256': _sha_file(bundle / 'sparse_index.csr.npz'),
            'verse_ids_sha256': _sha_file(bundle / 'verse_ids.npy'),
            'colbert_pack_id': sha256_text(canonical({k: v['sha256'] for k, v in sorted(pack['shards'].items())})),
            'colbert_dtype': pack['dtype'],
        },
        'fusion': FUSION,
        'candidate_language': 'english',
    }


def main():
    ext = ROOT / '.artifact-staging' / 'import-application-v1' / 'extracted'
    parts = identity_from_artifacts(
        ROOT / 'generated-artifacts' / 'onnx-int8' / 'bge_m3_multi_int8_matmul_gather.onnx',
        ROOT / 'generated-artifacts' / 'colbert-pack-v1' / 'manifest.json',
        ext / 'scripture-retrieval-english-v1', ext / 'bge-m3-pinned',
        ext / 'scripture-genome-question-hidden4096-optimized' / 'head_fp16.npz', ext / 'bge-m3-pinned' / 'tokenizer.json')
    print(json.dumps(parts, indent=1))
    print('configurationId (semantic, whole corpus):', configuration_id({**parts, 'filter_sha256': None}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
