"""Assemble the engine pack: everything the native engine reads that is not scripture text (docs/ENGINE_PLAN.md 2b).

  engine-pack/
    manifest.json           format, file sizes + SHA-256, identity parts (configuration identity), profiles
    encoder/<graph>.onnx(+.data)   INT8 query encoder (original file names: the graph references its data file)
    tokenizer.json
    head.npz                FP16 genome head
    retrieval/              verse_ids, dense, weighted genome, sparse index, gene ids
    entities.db             optional, gated people index (machine-generated, unreviewed)
The ColBERT token pack is a separate optional pack (generated-artifacts/colbert-pack-v1) and keeps its own manifest.

Files are hard-linked when the output is on the same volume as the sources, otherwise copied.

  .venv\\Scripts\\python.exe -I tool/build_engine_pack.py [--out generated-artifacts/engine-pack] [--variant int8_matmul]
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config_identity as ci  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / '.artifact-staging' / 'import-application-v1' / 'extracted'
VARIANT_FILES = {'int8_matmul': 'bge_m3_multi_int8_matmul.onnx', 'int8_matmul_gather': 'bge_m3_multi_int8_matmul_gather.onnx'}
RETRIEVAL = ('verse_ids.npy', 'dense_embeddings.f16.npy', 'weighted_genome_embeddings.f16.npy', 'sparse_index.csr.npz', 'gene_ids.txt')


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 22), b''):
            h.update(c)
    return h.hexdigest()


def place(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default=str(ROOT / 'generated-artifacts' / 'engine-pack'))
    ap.add_argument('--variant', default='int8_matmul', choices=list(VARIANT_FILES))
    ap.add_argument('--entities', default=str(ROOT / '.artifact-staging' / 'entities.db'))
    a = ap.parse_args()
    out = Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    graph = ROOT / 'generated-artifacts' / 'onnx-int8' / VARIANT_FILES[a.variant]
    # the graph names its external-data file, so both keep their original file names
    plan = {f'encoder/{graph.name}': graph, f'encoder/{graph.name}.data': Path(str(graph) + '.data'),
            'tokenizer.json': EXT / 'bge-m3-pinned' / 'tokenizer.json',
            'head.npz': EXT / 'scripture-genome-question-hidden4096-optimized' / 'head_fp16.npz'}
    for n in RETRIEVAL:
        plan[f'retrieval/{n}'] = EXT / 'scripture-retrieval-english-v1' / n
    entities = Path(a.entities)
    if entities.exists():
        plan['entities.db'] = entities
    files = {}
    for rel, src in plan.items():
        place(src, out / rel)
        files[rel] = {'bytes': (out / rel).stat().st_size, 'sha256': sha256(out / rel)}
        print(f'{rel:36s}{files[rel]["bytes"]:>14,}', flush=True)

    base = json.loads((EXT / 'bge-m3-pinned' / 'manifest.json').read_text('utf-8'))
    pack_manifest = ROOT / 'generated-artifacts' / 'colbert-pack-v1' / 'manifest.json'
    pack = json.loads(pack_manifest.read_text('utf-8')) if pack_manifest.exists() else None
    identity = {
        'base_model_revision': base['revision'],
        'tokenizer_sha256': files['tokenizer.json']['sha256'],
        'encoder': {'graph_sha256': files[f'encoder/{graph.name}']['sha256'], 'data_sha256': files[f'encoder/{graph.name}.data']['sha256'],
                    'name': graph.name},
        'head_sha256': files['head.npz']['sha256'],
        'index': {'dense_sha256': files['retrieval/dense_embeddings.f16.npy']['sha256'],
                  'genome_sha256': files['retrieval/weighted_genome_embeddings.f16.npy']['sha256'],
                  'sparse_sha256': files['retrieval/sparse_index.csr.npz']['sha256'],
                  'verse_ids_sha256': files['retrieval/verse_ids.npy']['sha256'],
                  'colbert_pack_id': ci.sha256_text(ci.canonical({k: v['sha256'] for k, v in sorted(pack['shards'].items())})) if pack else None,
                  'colbert_dtype': pack['dtype'] if pack else None},
        'fusion': {k: v for k, v in ci.FUSION.items() if k != 'weights'},
        'candidate_language': 'english',
    }
    profiles = json.loads((ROOT / 'tool' / 'data' / 'fusion_profiles.json').read_text('utf-8'))
    manifest = {'format': 'engine-pack-v1', 'variant': a.variant, 'encoder_file': f'encoder/{graph.name}', 'files': files, 'identity': identity,
                'profiles': {k: [v['echo'], v['spark'], v['thread'], v['root']] for k, v in profiles['profiles'].items()},
                'default_profile': profiles['default'], 'fallback_without_thread': profiles['fallback_without_thread'],
                'colbert_pack_manifest_sha256': sha256(pack_manifest) if pack else None}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=1, ensure_ascii=False), 'utf-8')
    print(f'engine pack: {sum(f["bytes"] for f in files.values()) / 1e9:.2f} GB at {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
