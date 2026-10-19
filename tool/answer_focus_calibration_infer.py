"""Frozen native inference inputs for the learned Answer Focus experiment.

python -I tool/answer_focus_calibration_infer.py train|calibration|test
No fitting, automatic grading, application mutations or downloads.
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
import answer_focus_wide_pool as wide

OUT = ROOT / 'local-benchmarks/answer-focus-calibration'
QUESTIONS = ROOT / 'tool/answer_focus_calibration_questions.json'


def questions():
    old = wide.read(wide.OLD / 'rankings.json')['rankings']
    train = [{**{k: r[k] for k in ('id', 'query', 'language')}, 'split': 'train', 'kind': 'answerable'}
             for r in old if r['kind'] != 'absent']
    fresh = wide.read(QUESTIONS)['queries']
    rows = train + fresh
    assert len({r['id'] for r in rows}) == len(rows)
    assert len({r['query'].strip().casefold() for r in rows}) == len(rows), 'Duplicate questions'
    assert len(train) == 72 and sum(r['split'] == 'calibration' for r in fresh) == 8
    assert sum(r['split'] == 'test' for r in fresh) == 10
    return rows


def identity():
    paths = [Path(__file__), QUESTIONS, ROOT / 'docs/ANSWER_FOCUS_CALIBRATION_PROTOCOL.md',
             ROOT / 'tool/answer_focus_wide_pool.py', ROOT / 'tool/reranker_stage2.py',
             ROOT / 'engine/target/release/scripture_engine.dll',
             wide.GEN / 'answer-focus-int8-v1/model.onnx', wide.GEN / 'answer-focus-int8-v1/tokenizer.json',
             wide.GEN / 'engine-pack/manifest.json', wide.GEN / 'colbert-pack-v1/manifest.json',
             wide.GEN / 'release/content.db', wide.GEN / 'release/catalog.db',
             ROOT / 'tool/search_anchors_v2.json', wide.OLD / 'rankings.json',
             wide.OLD / 'grades.json', wide.OLD / 'blind-sheet.json',
             ROOT / 'local-benchmarks/reranker-speed/grades.json',
             ROOT / 'local-benchmarks/reranker-speed/blind-sheet.json',
             wide.OUT / 'grades.json', wide.OUT / 'blind-sheet.json', wide.OUT / 'identity.json']
    return {'sha256': {str(p.relative_to(ROOT)): wide.digest(p) for p in paths},
            'candidate_depth': 200, 'backend': 'native_cpu_int8_single_pair'}


def infer(split):
    ident = identity()
    if (OUT / 'identity.json').exists():
        assert wide.read(OUT / 'identity.json') == ident, 'Input drift; do not mix runs'
    wide.write(OUT / 'identity.json', ident)
    qs = questions()
    wide.write(OUT / 'splits.json', qs)
    corpus = wide.Corpus()
    grade = wide.judgments(corpus)
    previous_ident = wide.read(wide.OUT / 'identity.json')['hashes']
    for relative in ('generated-artifacts/answer-focus-int8-v1/model.onnx',
                     'generated-artifacts/answer-focus-int8-v1/tokenizer.json',
                     'engine/target/release/scripture_engine.dll'):
        key = str(Path(relative))
        assert previous_ident[key] == ident['sha256'][key], 'Pilot score reuse identity mismatch'
    old = {r['id']: r for r in wide.read(wide.OLD / 'rankings.json')['rankings']}
    selected = [r for r in qs if r['split'] == split]
    native = wide.Native()
    try:
        for i, q in enumerate(selected):
            path = OUT / 'queries' / split / (q['id'] + '.json')
            if path.exists() and wide.read(path)['complete']:
                print(f"cached {split} {i+1}/{len(selected)} {q['id']}", flush=True)
                continue
            r = native.request(op='semantic', query=q['query'], language=q['language'], profile='compass', top_k=200)
            ids = [h['verse_id'] for h in r['hits']]
            assert len(ids) == 200 and len(set(ids)) == 200
            if split == 'train':
                assert ids[:30] == old[q['id']]['candidates'], ('Historical drift', q['id'])
            texts = [corpus.text(v, q['language']) for v in ids]
            text_hash = hashlib.sha256(json.dumps(texts, ensure_ascii=False).encode()).hexdigest()
            labels = [grade(q['id'], v) if split == 'train' else None for v in ids]
            eligible = [j for j in range(200) if split != 'train' or labels[j] is not None]
            if path.exists():
                row = wide.read(path)
                assert row['candidates'] == ids and row['text_sha256'] == text_hash and row['grades'] == labels
            else:
                row = {**q, 'candidates': ids, 'compass': [h['score'] for h in r['hits']],
                       'reranker': [None]*200, 'grades': labels, 'complete': False,
                       'text_sha256': text_hash, 'batches': [], 'reused_pairs': 0}
                cached = wide.OUT / 'queries' / (q['id'] + '.json')
                if split == 'train' and cached.exists():
                    c = wide.read(cached)
                    assert c['query'] == q['query'] and c['language'] == q['language'] and c['complete']
                    by = dict(zip(c['candidates'], c['reranker']))
                    for j in eligible:
                        row['reranker'][j] = by[ids[j]]
                        row['reused_pairs'] += 1
            remaining = [j for j in eligible if row['reranker'][j] is None]
            for start in range(0, len(remaining), 10):
                js = remaining[start:start+10]
                t = time.perf_counter()
                got = native.request(op='focus', query=q['query'], texts=[texts[j] for j in js])
                assert got['device'] == 'cpu' and len(got['scores']) == len(js)
                assert np.isfinite(got['scores']).all()
                for j, score in zip(js, got['scores']):
                    row['reranker'][j] = score
                row['batches'].append({'indices': js, 'seconds': time.perf_counter()-t})
                wide.write(path, row)
            row['complete'] = all(row['reranker'][j] is not None for j in eligible)
            assert row['complete'] and eligible
            wide.write(path, row)
            print(f"{split} {i+1}/{len(selected)} {q['id']}: {len(eligible)} scored ({row['reused_pairs']} reused)", flush=True)
    finally:
        native.close()


def rows(split):
    qs = [q for q in questions() if q['split'] == split]
    result = [wide.read(OUT / 'queries' / split / (q['id'] + '.json')) for q in qs]
    assert all(r['complete'] for r in result), 'Inference incomplete'
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('split', choices=('train', 'calibration', 'test'))
    infer(p.parse_args().split)
