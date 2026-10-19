"""Offline, resumable Answer Focus candidate-depth experiment; never imported by the app."""
import argparse
import ctypes
import hashlib
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from scipy import sparse
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
from mathematical_retrieval_experiment import TokenPack, digest, norm, order, z
from reranker_stage2 import Corpus
from volume_balance import balance, volume_of_rows

OUT = ROOT / 'local-benchmarks/answer-focus-wide-pool'
OLD = ROOT / 'local-benchmarks/reranker-stage2'
GEN = ROOT / 'generated-artifacts'
DEPTHS = (10, 15, 20, 30, 60, 120, 200)


def read(p):
    return json.loads(Path(p).read_text('utf-8-sig'))


def write(p, value):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1, allow_nan=False), 'utf-8')
    tmp.replace(p)


def selected():
    rows = read(OLD / 'rankings.json')['rankings']
    key = lambda r: hashlib.sha256(('20261018:' + r['id']).encode()).hexdigest()
    groups = [([r for r in rows if r['split'] == 'development'], 4),
              ([r for r in rows if r['split'] == 'fresh' and r['kind'] != 'absent' and r['language'] == 'english'], 3),
              ([r for r in rows if r['language'] == 'spanish'], 1),
              ([r for r in rows if r['kind'] == 'absent'], 2)]
    return [r for group, n in groups for r in sorted(group, key=key)[:n]]


def judgments(corpus):
    by = {}
    for q in read(ROOT / 'tool/search_anchors_v2.json')['queries']:
        for a in q['anchors']:
            by[q['id'], a['reference']] = a['grade']
    for folder in (OLD, ROOT / 'local-benchmarks/reranker-speed'):
        gs = read(folder / 'grades.json')
        for it in read(folder / 'blind-sheet.json'):
            key = (it['question_id'], it['reference'])
            g = gs[it['item']]['grade']
            assert g in (0, 1, 2), (key, g)
            if key in by:
                assert by[key] == g, ('Conflicting historical grades', key)
            by[key] = g
    if (OUT / 'grades.json').exists():
        sheet = read(OUT / 'blind-sheet.json')
        grades = read(OUT / 'grades.json')
        assert grades['sheet_sha256'] == digest(OUT / 'blind-sheet.json'), 'Stale review'
        expected = {it['item'] for it in sheet}
        assert set(grades['items']) == expected, 'Missing/extra review IDs'
        for it in sheet:
            g = grades['items'][it['item']]
            if g['grade'] is not None:
                assert g['grade'] in (0, 1, 2) and g['reason'].strip()
                key = (it['question_id'], it['reference'])
                assert key not in by or by[key] == g['grade']
                by[key] = g['grade']
    return lambda q, v: by.get((q, corpus.ref(v)))


def filter_stats(q, ids, scores, grade):
    scores = np.asarray(scores, dtype=float)
    keep = scores > scores.mean()
    gs = [grade(q, v) for v in ids]
    return {'count': len(ids), 'retained': int(keep.sum()),
            'known_direct_before': sum(g == 2 for g in gs),
            'known_direct_retained': sum(g == 2 and bool(k) for g, k in zip(gs, keep)),
            'known_direct_discarded': sum(g == 2 and not k for g, k in zip(gs, keep)),
            'retained_judged': sum(g is not None and bool(k) for g, k in zip(gs, keep)),
            'retained_known_nonanswers': sum(g == 0 and bool(k) for g, k in zip(gs, keep)),
            'retained_ids': [int(v) for v, k in zip(ids, keep) if k]}


def audit():
    corpus = Corpus()
    grade = judgments(corpus)
    out = []
    for r in read(OLD / 'rankings.json')['rankings']:
        if r['candidates']:
            a = filter_stats(r['id'], r['candidates'], r['score_B'], grade)
            out.append({'id': r['id'], 'kind': r['kind'], 'split': r['split'], **a})
    answerable = [r for r in out if r['kind'] != 'absent']
    summary = {k: sum(r[k] for r in answerable) for k in
               ('count', 'retained', 'known_direct_before', 'known_direct_retained',
                'known_direct_discarded', 'retained_judged', 'retained_known_nonanswers')}
    summary['questions'] = len(answerable)
    summary['absent_return_counts'] = {r['id']: r['retained'] for r in out if r['kind'] == 'absent'}
    write(OUT / 'existing-30-audit.json', {'scope': 'Historical fp32 stage-2 scores; incomplete labels; not production int8.',
                                        'summary': summary, 'questions': out})
    print(json.dumps(summary, indent=1), flush=True)


class Native:
    def __init__(self):
        self.lib = ctypes.CDLL(str(ROOT / 'engine/target/release/scripture_engine.dll'))
        self.lib.se_open.restype = ctypes.c_void_p
        self.lib.se_open.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_char_p)]
        self.lib.se_request.restype = ctypes.c_void_p
        self.lib.se_request.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        self.lib.se_free_string.argtypes = [ctypes.c_void_p]
        self.lib.se_close.argtypes = [ctypes.c_void_p]
        pack = GEN / 'engine-pack'
        m = read(pack / 'manifest.json')
        cfg = {'retrieval_dir': str(pack / 'retrieval'), 'head_npz': str(pack / 'head.npz'),
               'encoder_model': str(pack / m['encoder_file']), 'tokenizer_json': str(pack / 'tokenizer.json'),
               'pack_dir': str(GEN / 'colbert-pack-v1'), 'profiles': m['profiles'],
               'default_profile': m['default_profile'], 'fallback_without_thread': m['fallback_without_thread'],
               'identity': m['identity'], 'threads': 4, 'volume_balance': .75,
               'focus_model': str(GEN / 'answer-focus-int8-v1/model.onnx'),
               'focus_tokenizer': str(GEN / 'answer-focus-int8-v1/tokenizer.json'), 'focus_device': 'cpu'}
        err = ctypes.c_char_p()
        self.handle = self.lib.se_open(json.dumps(cfg).encode(), ctypes.byref(err))
        assert self.handle, err.value

    def request(self, **payload):
        p = self.lib.se_request(self.handle, json.dumps({'request_id': 1, **payload}).encode())
        assert p
        try:
            r = json.loads(ctypes.string_at(p))
        finally:
            self.lib.se_free_string(p)
        assert 'error' not in r, r
        return r

    def close(self):
        self.lib.se_close(self.handle)


def identity(rows):
    files = [Path(__file__), ROOT / 'docs/ANSWER_FOCUS_WIDE_POOL_PROTOCOL.md',
             ROOT / 'tool/retrieval_v2.py', ROOT / 'tool/mathematical_retrieval_experiment.py',
             ROOT / 'tool/volume_balance.py', ROOT / 'tool/reranker_stage2.py',
             ROOT / 'engine/target/release/scripture_engine.dll',
             GEN / 'answer-focus-int8-v1/model.onnx', GEN / 'answer-focus-int8-v1/tokenizer.json',
             GEN / 'engine-pack/manifest.json', GEN / 'colbert-pack-v1/manifest.json',
             GEN / 'release/content.db', GEN / 'release/catalog.db', OLD / 'rankings.json']
    return {'hashes': {str(p.relative_to(ROOT)): digest(p) for p in files},
            'selected_ids': [r['id'] for r in rows], 'depths': list(DEPTHS), 'backend': 'native_cpu_int8_single_pair'}


def run():
    import retrieval_v2 as ref
    rows = selected()
    ident = identity(rows)
    if (OUT / 'identity.json').exists():
        assert read(OUT / 'identity.json') == ident, 'Changed inputs/code: use a new output directory'
    write(OUT / 'identity.json', ident)
    write(OUT / 'selection.json', [{k: r[k] for k in ('id', 'query', 'language', 'split', 'kind')} for r in rows])
    ret = GEN / 'engine-pack/retrieval'
    ids = np.load(ret / 'verse_ids.npy')
    dense = np.load(ret / 'dense_embeddings.f16.npy').astype(np.float32)
    genome = norm(np.load(ret / 'weighted_genome_embeddings.f16.npy').astype(np.float32))
    sp = sparse.load_npz(ret / 'sparse_index.csr.npz').astype(np.float32)
    vol = volume_of_rows(ids)
    ref.OUT = OUT / 'encoding'
    ref.OUT.mkdir(parents=True, exist_ok=True)
    encoded = ref.encode_queries(SimpleNamespace(S=sp), rows)
    pack, corpus, native = TokenPack(), Corpus(), Native()
    weights = np.array(read(GEN / 'engine-pack/manifest.json')['profiles']['compass'])
    try:
        for qi, q in enumerate(rows):
            path = OUT / 'queries' / (q['id'] + '.json')
            if path.exists() and read(path)['complete']:
                print(f"cached {qi+1}/{len(rows)} {q['id']}", flush=True)
                continue
            da = balance(dense @ encoded[f'd{qi}'], vol, np.ones(len(ids), bool), .75)
            ga = balance(genome @ encoded[f'gw{qi}'], vol, np.ones(len(ids), bool), .75)
            sa = encoded[f's{qi}']
            cand = np.unique(np.r_[order(da, ids, 200), order(ga, ids, 200), order(sa, ids, 200)])
            co = pack.maxsim(encoded[f'c{qi}'], cand)
            score = weights @ np.array([z(da[cand]), z(sa[cand]), z(co), z(ga[cand])])
            rank = order(score, ids[cand])
            candidates = ids[cand[rank]].tolist()
            compass = score[rank].tolist()
            check = native.request(op='semantic', query=q['query'], language=q['language'], profile='compass', top_k=200)
            assert candidates[:200] == [h['verse_id'] for h in check['hits']], ('Native parity failed', q['id'])
            assert candidates[:30] == q['candidates'], ('Historical candidate drift', q['id'])
            texts = [corpus.text(v, q['language']) for v in candidates]
            text_hash = hashlib.sha256(json.dumps(texts, ensure_ascii=False).encode()).hexdigest()
            if path.exists():
                row = read(path)
                assert row['candidates'] == candidates and row['text_sha256'] == text_hash
            else:
                row = {k: q[k] for k in ('id', 'query', 'language', 'split', 'kind')}
                row.update(candidates=candidates, compass=compass, reranker=[], batches=[], complete=False,
                           native_top200_exact=True, text_sha256=text_hash)
            for start in range(len(row['reranker']), len(candidates), 10):
                t = time.perf_counter()
                r = native.request(op='focus', query=q['query'], texts=texts[start:start+10])
                assert r['device'] == 'cpu' and len(r['scores']) == len(texts[start:start+10])
                assert np.isfinite(r['scores']).all()
                row['reranker'].extend(r['scores'])
                row['batches'].append({'start': start, 'count': len(r['scores']), 'seconds': time.perf_counter()-t})
                row['complete'] = len(row['reranker']) == len(candidates)
                write(path, row)
                print(f"{qi+1}/{len(rows)} {q['id']} scored {len(row['reranker'])}/{len(candidates)}", flush=True)
    finally:
        native.close()


def variants(row):
    assert row['complete']
    for depth in (*DEPTHS, len(row['candidates'])):
        n = min(depth, len(row['candidates']))
        ids = np.array(row['candidates'][:n])
        rr = np.array(row['reranker'][:n])
        cp = np.array(row['compass'][:n])
        for name, s in [('compass', cp), ('reranker', rr), ('blend', .5*z(cp)+.5*z(rr))]:
            # Stable ties retain Compass order, as in the app.
            ranked = ids[np.argsort(-s, kind='stable')].tolist()
            yield f'{name}@{depth}', ids.tolist(), s, ranked


def complete_rows():
    rows = [read(p) for p in sorted((OUT / 'queries').glob('*.json'))]
    assert len(rows) == len(selected()) and all(r['complete'] for r in rows), 'Inference incomplete'
    return rows


def review():
    corpus = Corpus()
    grade = judgments(corpus)
    if (OUT / 'blind-sheet.json').exists():
        print('Review sheet already exists; preserved.', flush=True)
        return
    items = []
    for row in complete_rows():
        if row['kind'] == 'absent':
            continue
        pooled = {v for _, _, _, ranked in variants(row) for v in ranked[:5]}
        for v in sorted(pooled):
            if grade(row['id'], v) is not None:
                continue
            items.append({'question_id': row['id'], 'query': row['query'], 'verse_id': v,
                          'reference': corpus.ref(v), 'language': row['language'],
                          'context': [{'reference': corpus.ref(u), 'focal': u == v, 'text': text}
                                      for u, text in corpus.window(v, row['language'])]})
    rng = np.random.default_rng(20261018)
    rng.shuffle(items)
    for i, it in enumerate(items):
        it['item'] = f'w{i:04d}'
    write(OUT / 'blind-sheet.json', items)
    write(OUT / 'grades.json', {'sheet_sha256': digest(OUT / 'blind-sheet.json'),
                               'items': {it['item']: {'grade': None, 'reason': ''} for it in items}})
    print(f'{len(items)} new top-five judgments required', flush=True)


def report():
    corpus = Corpus()
    grade = judgments(corpus)
    results = []
    for row in complete_rows():
        metrics = {}
        for name, ids, s, ranked in variants(row):
            gs = [grade(row['id'], v) for v in ranked[:5]]
            top = {'judged': sum(g is not None for g in gs), 'count': len(gs)}
            if row['kind'] != 'absent' and all(g is not None for g in gs):
                top.update(direct_p5=sum(g == 2 for g in gs)/5, related_p5=sum(g >= 1 for g in gs)/5,
                           any_direct=any(g == 2 for g in gs))
            metrics[name] = {'top5': top, 'mean_filter': filter_stats(row['id'], ids, s, grade)}
        results.append({'id': row['id'], 'kind': row['kind'], 'pool': len(row['candidates']),
                        'seconds': sum(b['seconds'] for b in row['batches']), 'methods': metrics})
    write(OUT / 'report.json', {'scope': 'Exploratory reused-question pilot; mean-filter statistics are conditional on known labels.',
                               'questions': results})
    print(f'Report saved for {len(results)} questions; incomplete top-five grades are not scored.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('audit', 'run', 'review', 'report'))
    args = parser.parse_args()
    with threadpool_limits(limits=4):
        globals()[args.command]()
