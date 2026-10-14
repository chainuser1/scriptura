"""Build the English precomputed ColBERT token pack (PLAN section 8) with the FP32 reference graph.

Layout (generated-artifacts/colbert-pack-v1/, gitignored):
  shard-NNNN.vec.npy     float16 [tokens_in_shard, 1024]  token vectors, verse rows contiguous, CLS dropped, </s> kept
  shard-NNNN.cnt.npy     int32   [verses_in_shard]        retained token count per verse row
  manifest.json          identities, retention rule, per-shard sha256, totals
Rows follow verse_ids.npy order, SHARD verses per shard. Resumable: a finished shard is never recomputed.
Passage side is FP32-encoded on purpose: the pack is built offline, only the QUERY encoder runs on-device.

  .venv\\Scripts\\python.exe -I tool/build_colbert_pack.py [--limit N]
"""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
from transformers import AutoTokenizer

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / '.artifact-staging' / 'import-application-v1' / 'extracted'
ONNX = ROOT / 'generated-artifacts' / 'onnx-fp32' / 'bge_m3_multi_fp32.onnx'
OUT = ROOT / 'generated-artifacts' / 'colbert-pack-v1'
SHARD = 1000


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 22), b''):
            h.update(c)
    return h.hexdigest()


def save_atomic(arr, path):
    tmp = Path(str(path) + '.tmp')
    with open(tmp, 'wb') as f:
        np.save(f, arr, allow_pickle=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--limit', type=int, default=0, help='only the first N verses (smoke test; no manifest)')
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    r = EXT / 'scripture-retrieval-english-v1'
    verse_ids = np.load(r / 'verse_ids.npy', allow_pickle=False)
    texts = [json.loads(l)['scripture_text'] for l in (r / 'scripture_text.jsonl').read_text('utf-8').splitlines()]
    n = a.limit or len(texts)
    tok = AutoTokenizer.from_pretrained(EXT / 'bge-m3-pinned')
    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    sess = ort.InferenceSession(str(ONNX), so, providers=['CPUExecutionProvider'])

    n_shards = (n + SHARD - 1) // SHARD
    t0, done_v = time.perf_counter(), 0
    for sh in range(n_shards):
        vec_p, cnt_p = OUT / f'shard-{sh:04d}.vec.npy', OUT / f'shard-{sh:04d}.cnt.npy'
        lo, hi = sh * SHARD, min(n, (sh + 1) * SHARD)
        if vec_p.exists() and cnt_p.exists():
            continue
        lens = np.array([len(x) for x in tok(texts[lo:hi], truncation=False)['input_ids']])
        assert lens.max() <= 512, 'passage over 512 tokens'
        order = np.argsort(lens, kind='stable')
        per = [None] * (hi - lo)
        for s in range(0, len(order), 16):
            idx = order[s:s + 16]
            e = tok([texts[lo + i] for i in idx], padding=True, return_tensors='np', truncation=False)
            _, _, c = sess.run(None, {'input_ids': e['input_ids'].astype(np.int64), 'attention_mask': e['attention_mask'].astype(np.int64)})
            for j, i in enumerate(idx):
                k = int(e['attention_mask'][j].sum()) - 1
                per[i] = c[j, :k].astype(np.float16)
        counts = np.array([len(x) for x in per], dtype=np.int32)
        assert (counts == lens - 1).all()
        save_atomic(np.concatenate(per, axis=0), vec_p)
        save_atomic(counts, cnt_p)
        done_v += hi - lo
        el = time.perf_counter() - t0
        print(f'shard {sh + 1}/{n_shards}  {hi}/{n} verses  {el / 60:.1f} min  ETA {(n - hi) * el / max(done_v, 1) / 60:.1f} min', flush=True)

    if a.limit:
        print('smoke test only; no manifest')
        return 0
    counts = np.concatenate([np.load(OUT / f'shard-{s:04d}.cnt.npy') for s in range(n_shards)])
    total = int(counts.sum())
    shards = {}
    for s in range(n_shards):
        for suffix in ('vec', 'cnt'):
            p = OUT / f'shard-{s:04d}.{suffix}.npy'
            shards[p.name] = {'bytes': p.stat().st_size, 'sha256': sha256(p)}
    manifest = {
        'format': 'colbert-pack-v1', 'rows': int(len(counts)), 'dim': 1024, 'dtype': 'float16', 'shard_verses': SHARD,
        'total_tokens': total, 'min_tokens': int(counts.min()), 'max_tokens': int(counts.max()),
        'retention': 'CLS position dropped; </s> kept; padding excluded; vectors L2-normalized (FP32 before FP16 cast)',
        'row_order': 'verse_ids.npy of scripture-retrieval-english-v1',
        'verse_ids_npy_sha256': sha256(r / 'verse_ids.npy'),
        'text_source_sha256': sha256(r / 'scripture_text.jsonl'),
        'encoder_graph_sha256': sha256(ONNX), 'encoder_data_sha256': sha256(Path(str(ONNX) + '.data')),
        'tokenizer_json_sha256': sha256(EXT / 'bge-m3-pinned' / 'tokenizer.json'),
        'base_revision': json.loads((EXT / 'bge-m3-pinned' / 'manifest.json').read_text('utf-8'))['revision'],
        'shards': shards,
    }
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=1), 'utf-8')
    print(f'pack complete: {total:,} token vectors, {sum(v["bytes"] for v in shards.values()) / 1e9:.2f} GB')
    return 0


if __name__ == '__main__':
    sys.exit(main())
