"""Reranker test, stage 2 (protocol: docs/RERANKER_STAGE2_PROTOCOL.md). Offline research; the app never loads this.

  .venv/Scripts/python.exe -I tool/reranker_stage2.py            candidates, reranking, blind sheet
  .venv/Scripts/python.exe -I tool/reranker_stage2.py --score    after grades.json is filled in

Rankings stay in rankings.json, which the judge does not open before grading. The blind sheet shows only questions
and verses, shuffled, without method, score or rank.
"""
import bisect
import ctypes
import json
import random
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
GEN = ROOT / 'generated-artifacts'
OUT = ROOT / 'local-benchmarks/reranker-stage2'
MODEL = 'BAAI/bge-reranker-v2-m3'
POOL, TOP, SEED = 30, 5, 20261017


def read(p):
    return json.loads(Path(p).read_text('utf-8'))


def write(p, x):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(x, ensure_ascii=False, indent=1), 'utf-8')


class Corpus:
    def __init__(self):
        cat = sqlite3.connect(f'file:{(GEN / "release/catalog.db").as_posix()}?mode=ro', uri=True)
        self.chapters = cat.execute('SELECT book_id, chapter, first_verse_id FROM chapters ORDER BY first_verse_id').fetchall()
        self.firsts = [c[2] for c in self.chapters]
        self.names = dict(cat.execute('SELECT book_id, name FROM book_names_english'))
        self.db = sqlite3.connect(f'file:{(GEN / "release/content.db").as_posix()}?mode=ro', uri=True)
        self.last = self.db.execute('SELECT max(verse_id) FROM text_english').fetchone()[0]

    def chapter(self, v):
        i = bisect.bisect_right(self.firsts, v) - 1
        end = self.firsts[i + 1] - 1 if i + 1 < len(self.firsts) else self.last
        return self.chapters[i], end

    def ref(self, v):
        (b, ch, start), _ = self.chapter(v)
        return f'{self.names[b]} {ch}:{v - start + 1}'

    def text(self, v, lang):
        return self.db.execute(f'SELECT text FROM text_{lang} WHERE verse_id=?', (v,)).fetchone()[0]

    def window(self, v, lang):
        (_, _, start), end = self.chapter(v)
        return [(u, self.text(u, lang)) for u in (v - 1, v, v + 1) if start <= u <= end]


class Engine:
    def __init__(self):
        lib = ctypes.CDLL(str(ROOT / 'engine/target/release/scripture_engine.dll'))
        lib.se_open.restype = ctypes.c_void_p
        lib.se_open.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_char_p)]
        lib.se_request.restype = ctypes.c_void_p
        lib.se_request.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        lib.se_free_string.argtypes = [ctypes.c_void_p]
        lib.se_close.argtypes = [ctypes.c_void_p]
        pack = GEN / 'engine-pack'
        m = read(pack / 'manifest.json')
        cfg = {'retrieval_dir': str(pack / 'retrieval'), 'head_npz': str(pack / 'head.npz'),
               'encoder_model': str(pack / m['encoder_file']), 'tokenizer_json': str(pack / 'tokenizer.json'),
               'pack_dir': str(GEN / 'colbert-pack-v1'), 'topics_db': str(GEN / 'topics-pack-v1/topics.db'),
               'profiles': m['profiles'], 'default_profile': m['default_profile'],
               'fallback_without_thread': m['fallback_without_thread'], 'identity': m['identity'],
               'threads': 4, 'volume_balance': .75}  # as lib/services/engine/engine_pack.dart
        err = ctypes.c_char_p()
        self.lib, self.h = lib, lib.se_open(json.dumps(cfg).encode(), ctypes.byref(err))
        assert self.h, err.value

    def search(self, query, lang):
        p = self.lib.se_request(self.h, json.dumps({'op': 'search', 'query': query, 'profile': 'compass', 'top_k': POOL,
                                                    'language': lang, 'request_id': 1}).encode())
        try:
            r = json.loads(ctypes.string_at(p))
        finally:
            self.lib.se_free_string(p)
        assert 'error' not in r, r
        return [h['verse_id'] for h in r.get('hits', [])], r.get('mode')


def questions():
    dev = [{'id': q['id'], 'query': q['query'], 'language': 'english', 'split': 'development', 'kind': q.get('split')}
           for q in read(ROOT / 'tool/search_anchors_v2.json')['queries']]
    fresh = [{**q, 'split': 'fresh'} for q in read(ROOT / 'tool/reranker_fresh_set.json')['queries']]
    return dev + fresh


def run():
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    torch.set_num_threads(4)
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL).eval()
    corpus, engine = Corpus(), Engine()

    def scores(query, passages):
        with torch.inference_mode():
            x = tok([[query, p] for p in passages], padding=True, truncation=True, max_length=512, return_tensors='pt')
            return model(**x).logits.view(-1).float().tolist()

    def rerank(cands, s):
        return [v for _, _, v in sorted((-sc, i, v) for i, (v, sc) in enumerate(zip(cands, s)))]  # ties: engine order

    rankings, seconds = [], []
    for n, q in enumerate(questions()):
        cands, mode = engine.search(q['query'], q['language'])
        row = {**q, 'mode': mode, 'candidates': cands, 'A': cands[:TOP]}
        if cands:
            t = time.perf_counter()
            sb = scores(q['query'], [corpus.text(v, q['language']) for v in cands])
            sc = scores(q['query'], [' '.join(t for _, t in corpus.window(v, q['language'])) for v in cands])
            seconds.append((time.perf_counter() - t) / 2)
            row.update(B=rerank(cands, sb)[:TOP], C=rerank(cands, sc)[:TOP], score_B=sb, score_C=sc)
        else:
            row.update(B=[], C=[])
        rankings.append(row)
        print(f'{n + 1}/{len(questions())} {q["id"]}', flush=True)
    write(OUT / 'rankings.json', {'model': MODEL, 'revision': getattr(model.config, '_commit_hash', None),
                                  'seconds_per_question_30': {'median': float(np.median(seconds)), 'max': float(max(seconds))},
                                  'rankings': rankings})
    sheet(rankings, corpus)


def known_grades():
    return {(q['id'], a['reference']): a for q in read(ROOT / 'tool/search_anchors_v2.json')['queries'] for a in q['anchors']}


def sheet(rankings, corpus):
    known, items = known_grades(), []
    for r in rankings:
        if r['kind'] == 'absent':
            continue
        for v in sorted({v for m in 'ABC' for v in r[m]}):
            ref = corpus.ref(v)
            if (r['id'], ref) in known:
                continue
            items.append({'question_id': r['id'], 'question': r['query'], 'verse_id': v, 'reference': ref,
                          'passage': [{'reference': corpus.ref(u), 'focal': u == v, 'text': t} for u, t in corpus.window(v, r['language'])]})
    random.Random(SEED).shuffle(items)
    for i, it in enumerate(items):
        it['item'] = f'i{i:04d}'
    write(OUT / 'blind-sheet.json', items)
    write(OUT / 'grades.json', {it['item']: {'grade': None, 'reason': ''} for it in items})
    print(f'{len(items)} passages to grade -> {OUT / "blind-sheet.json"}')


def score():
    data, corpus = read(OUT / 'rankings.json'), Corpus()
    grades = read(OUT / 'grades.json')
    assert all(g['grade'] in (0, 1, 2) and g['reason'] for g in grades.values()), 'ungraded items'
    by = {(it['question_id'], it['verse_id']): grades[it['item']]['grade'] for it in read(OUT / 'blind-sheet.json')}
    known = known_grades()

    def grade(q, v):
        k = known.get((q, corpus.ref(v)))
        return k['grade'] if k else by[(q, v)]

    def metrics(rows, m):
        out = []
        for r in rows:
            g = [grade(r['id'], v) for v in r[m]] + [0] * (TOP - len(r[m]))
            ideal = sorted([grade(r['id'], v) for v in {v for x in 'ABC' for v in r[x]}], reverse=True)[:TOP]
            dcg = lambda gs: sum((0, 1, 3)[x] / np.log2(i + 2) for i, x in enumerate(gs))
            out.append((sum(x == 2 for x in g) / TOP, sum(x >= 1 for x in g) / TOP, float(any(x == 2 for x in g)),
                        dcg(g) / dcg(ideal) if dcg(ideal) else 0.0))
        return np.array(out)

    rows = data['rankings']
    dev = [r for r in rows if r['split'] == 'development']
    fresh = [r for r in rows if r['split'] == 'fresh' and r['kind'] != 'absent']
    report = {'model': data['model'], 'revision': data['revision'], 'timing': data['seconds_per_question_30']}
    names = ['direct_p5', 'related_p5', 'any_direct', 'ndcg5']
    for label, set_ in (('development', dev), ('fresh', fresh), ('fresh_spanish', [r for r in fresh if r['language'] == 'spanish'])):
        report[label] = {m: dict(zip(names, metrics(set_, m).mean(0).round(4).tolist())) for m in 'ABC'}
        report[label]['questions'] = len(set_)
    d = report['development']
    chosen = 'B' if d['B']['direct_p5'] > d['C']['direct_p5'] else 'C'
    a, c = metrics(fresh, 'A'), metrics(fresh, chosen)
    diff = c[:, 0] - a[:, 0]
    rng = np.random.default_rng(SEED)
    boot = np.array([diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(10000)])
    lo, hi = np.percentile(boot, [2.5, 97.5])
    gain, related_drop = diff.mean(), a[:, 1].mean() - c[:, 1].mean()
    report['decision'] = {'chosen': chosen, 'direct_gain': round(float(gain), 4), 'ci95': [round(float(lo), 4), round(float(hi), 4)],
                          'related_drop': round(float(related_drop), 4),
                          'pass': bool(gain >= .10 and lo > 0 and related_drop <= .05)}
    report['absent'] = [{'query': r['query'], 'mode': r['mode'], **{m: [corpus.ref(v) for v in r[m]] for m in 'ABC'},
                         'top_reranker_score': max(r.get('score_B') or [None])} for r in rows if r['kind'] == 'absent']
    report['per_question_fresh'] = [{'id': r['id'], 'A': metrics([r], 'A')[0, 0], chosen: metrics([r], chosen)[0, 0]} for r in fresh]
    write(OUT / 'report.json', report)
    print(json.dumps({k: report[k] for k in ('timing', 'development', 'fresh', 'fresh_spanish', 'decision')}, indent=1))


if __name__ == '__main__':
    score() if '--score' in sys.argv else run()
