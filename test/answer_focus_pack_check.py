"""Checks the Answer focus packs (tool/build_answer_focus_pack.py) and their bucket index entries.

  .venv\\Scripts\\python.exe -I test/answer_focus_pack_check.py [--root ../scriptura/artifacts]
"""
import argparse
import hashlib
import json
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = json.loads((ROOT / 'test/golden/answer_focus_pairs.json').read_text('utf-8'))
# Against the fp32 reference. Measured drift: fp16 <= 0.001, int8 <= 0.51 (8-bit weights move logits; ranking quality on
# 72 graded questions was unchanged). A broken export is off by several points, which these limits and the order check catch.
TOLERANCE = {'answer-focus-int8-v1': 1.0, 'answer-focus-fp16-v1': 0.05}
FILES = {'model.onnx', 'tokenizer.json', 'LICENSE', 'manifest.json'}


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def check(bucket, pid, entry):
    import onnxruntime as ort
    zpath = bucket / f'{pid}.zip'
    assert zpath.exists(), f'missing {zpath}'
    raw = zpath.read_bytes()
    assert entry['archive'] == {'name': zpath.name, 'bytes': len(raw), 'sha256': sha256(raw)}, f'{pid}: index archive entry stale'
    assert entry['optional'] is True and entry['kind'] == pid.removesuffix('-v1'), entry
    with zipfile.ZipFile(zpath) as z, tempfile.TemporaryDirectory() as tmp:
        names = {n.split('/', 1)[1] for n in z.namelist() if not n.endswith('/')}
        assert names == FILES, f'{pid}: {sorted(names)} (a model with external data would add files)'
        assert all(n.startswith(f'{pid}/') for n in z.namelist()), f'{pid}: wrong top folder'
        z.extractall(tmp)
        d = Path(tmp) / pid
        manifest = json.loads((d / 'manifest.json').read_text('utf-8'))
        assert set(manifest['files']) == FILES - {'manifest.json'}, manifest['files'].keys()
        for name, m in manifest['files'].items():
            b = (d / name).read_bytes()
            assert (len(b), sha256(b)) == (m['bytes'], m['sha256']), f'{pid}/{name}: manifest mismatch'
        assert set(entry['files']) == FILES, entry['files'].keys()
        assert 'Apache License' in (d / 'LICENSE').read_text('utf-8'), 'licence text'
        sess = ort.InferenceSession(str(d / 'model.onnx'), providers=['CPUExecutionProvider'])
        got = []
        for p in GOLDEN['pairs']:
            ids = np.array([p['input_ids']], dtype=np.int64)
            got.append(float(sess.run(None, {'input_ids': ids, 'attention_mask': np.ones_like(ids)})[0].reshape(-1)[0]))
            assert abs(got[-1] - p['score']) <= TOLERANCE[pid], f'{pid}: {got[-1]:.3f} vs reference {p["score"]:.3f}'
        assert min(got[:2]) - got[2] > 3, f'{pid}: the unrelated verse must score far below the related ones: {got}'
        del sess
    print(f'{pid}: ok ({len(raw) / 2**20:.0f} MB)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=str(ROOT.parent / 'scriptura' / 'artifacts'))
    bucket = Path(ap.parse_args().root) / 'hosting' / 'bucket'
    index = json.loads((bucket / 'index.json').read_text('utf-8'))
    packs = {p['id']: p for p in index['packs']}
    for pid in TOLERANCE:
        assert pid in packs, f'index.json does not list {pid}'
        check(bucket, pid, packs[pid])
    print('answer focus packs: all checks passed')


if __name__ == '__main__':
    main()
