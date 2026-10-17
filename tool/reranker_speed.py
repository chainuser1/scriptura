"""Reranker cost test (after docs/RERANKER_STAGE2_RESULTS.md): ONNX export, int8 compression, fewer candidates.

  .venv/Scripts/python.exe -I tool/reranker_speed.py

Uses the stage-2 candidates and grades. Writes local-benchmarks/reranker-speed/report.json and a blind sheet of any top-5
passages that were never graded (grade them, then rerun with --score).
"""
import json
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
from reranker_stage2 import MODEL, SEED, TOP, Corpus, known_grades, read, write

STAGE2 = ROOT / 'local-benchmarks/reranker-stage2'
OUT = ROOT / 'local-benchmarks/reranker-speed'
THREADS = 4  # as the engine
KS = (30, 15, 10)


def export():
    fp32, int8 = OUT / 'fp32/model.onnx', OUT / 'int8/model.onnx'
    if not fp32.exists():
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        tok = AutoTokenizer.from_pretrained(MODEL)
        model = AutoModelForSequenceClassification.from_pretrained(MODEL).eval()
        x = tok([['question', 'passage text']], return_tensors='pt')
        fp32.parent.mkdir(parents=True, exist_ok=True)
        torch.onnx.export(model, (x['input_ids'], x['attention_mask']), str(fp32), input_names=['input_ids', 'attention_mask'],
                          output_names=['logits'], dynamic_axes={'input_ids': {0: 'b', 1: 's'}, 'attention_mask': {0: 'b', 1: 's'},
                                                                 'logits': {0: 'b'}}, opset_version=17, dynamo=False)
        tok.save_pretrained(OUT / 'tokenizer')
    if not int8.exists():
        from onnxruntime.quantization import QuantType, quantize_dynamic
        int8.parent.mkdir(parents=True, exist_ok=True)
        quantize_dynamic(str(fp32), str(int8), weight_type=QuantType.QInt8, use_external_data_format=True)
    return fp32, int8


def size(p):
    return sum(f.stat().st_size for f in p.parent.iterdir()) / 2**20


def run():
    import onnxruntime as ort
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    fp32, int8 = export()
    tok = AutoTokenizer.from_pretrained(OUT / 'tokenizer')
    corpus = Corpus()
    rows = [r for r in read(STAGE2 / 'rankings.json')['rankings'] if r['candidates'] and r['kind'] != 'absent']

    so = ort.SessionOptions()
    so.intra_op_num_threads, so.inter_op_num_threads = THREADS, 1
    sessions = {name: ort.InferenceSession(str(p), so, providers=['CPUExecutionProvider']) for name, p in (('onnx_fp32', fp32), ('onnx_int8', int8))}
    torch.set_num_threads(THREADS)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL).eval()

    def score(engine, q, texts):
        x = tok([[q, t] for t in texts], padding=True, truncation=True, max_length=512, return_tensors='np')
        if engine == 'torch_fp32':
            with torch.inference_mode():
                return model(input_ids=torch.from_numpy(x['input_ids']), attention_mask=torch.from_numpy(x['attention_mask'])).logits.view(-1).tolist()
        return sessions[engine].run(None, {'input_ids': x['input_ids'].astype(np.int64), 'attention_mask': x['attention_mask'].astype(np.int64)})[0].reshape(-1).tolist()

    out = {'sizes_mb': {'onnx_fp32': size(fp32), 'onnx_int8': size(int8)}, 'threads': THREADS, 'runs': {}}
    for engine in ('torch_fp32', 'onnx_fp32', 'onnx_int8'):
        for k in KS:
            if engine != 'onnx_int8' and k != 30:
                continue  # fewer candidates only for the compressed model
            times, tops = [], {}
            score(engine, rows[0]['query'], [corpus.text(v, rows[0]['language']) for v in rows[0]['candidates'][:k]])  # warm
            for r in rows:
                cands = r['candidates'][:k]
                t = time.perf_counter()
                s = score(engine, r['query'], [corpus.text(v, r['language']) for v in cands])
                times.append(time.perf_counter() - t)
                tops[r['id']] = [v for _, _, v in sorted((-x, i, v) for i, (v, x) in enumerate(zip(cands, s)))][:TOP]
            label = f'{engine}_k{k}'
            out['runs'][label] = {'median_s': float(np.median(times)), 'p90_s': float(np.percentile(times, 90)), 'top5': tops}
            print(label, round(float(np.median(times)), 2), 's median', flush=True)
    write(OUT / 'runs.json', out)
    sheet(rows, out, corpus)


def sheet(rows, out, corpus):
    known = known_grades()
    graded = {(it['question_id'], it['verse_id']) for it in read(STAGE2 / 'blind-sheet.json')}
    items = []
    for r in rows:
        new = {v for run in out['runs'].values() for v in run['top5'][r['id']]}
        for v in sorted(new):
            if (r['id'], v) in graded or (r['id'], corpus.ref(v)) in known:
                continue
            items.append({'question_id': r['id'], 'question': r['query'], 'verse_id': v, 'reference': corpus.ref(v),
                          'passage': [{'reference': corpus.ref(u), 'focal': u == v, 'text': t} for u, t in corpus.window(v, r['language'])]})
    random.Random(SEED + 1).shuffle(items)
    for i, it in enumerate(items):
        it['item'] = f'n{i:04d}'
    write(OUT / 'blind-sheet.json', items)
    print(f'{len(items)} new passages to grade')


def score():
    corpus, known = Corpus(), known_grades()
    old = {(it['question_id'], it['verse_id']): it['item'] for it in read(STAGE2 / 'blind-sheet.json')}
    g_old = read(STAGE2 / 'grades.json')
    new = {(it['question_id'], it['verse_id']): it['item'] for it in read(OUT / 'blind-sheet.json')}
    g_new = read(OUT / 'grades.json') if new else {}
    rows = {r['id']: r for r in read(STAGE2 / 'rankings.json')['rankings']}
    data = read(OUT / 'runs.json')

    def grade(q, v):
        k = known.get((q, corpus.ref(v)))
        if k:
            return k['grade']
        return g_old[old[(q, v)]]['grade'] if (q, v) in old else g_new[new[(q, v)]]['grade']

    report = {'sizes_mb': data['sizes_mb'], 'threads': data['threads'], 'methods': {}}
    a_fresh = {q: rows[q]['A'] for q in rows if rows[q]['split'] == 'fresh' and rows[q]['kind'] != 'absent'}
    for label, run in [('today_A', {'median_s': 0.0, 'top5': {q: rows[q]['A'] for q in rows if rows[q]['kind'] != 'absent'}})] + list(data['runs'].items()):
        res = {}
        for split in ('fresh', 'development'):
            ids = [q for q in run['top5'] if rows[q]['split'] == split]
            direct = [sum(grade(q, v) == 2 for v in run['top5'][q]) / TOP for q in ids]
            related = [sum(grade(q, v) >= 1 for v in run['top5'][q]) / TOP for q in ids]
            res[split] = {'direct_p5': round(float(np.mean(direct)), 4), 'related_p5': round(float(np.mean(related)), 4)}
        res['median_s'] = round(run['median_s'], 2)
        if label != 'today_A':
            diff = np.array([sum(grade(q, v) == 2 for v in run['top5'][q]) / TOP - sum(grade(q, v) == 2 for v in a_fresh[q]) / TOP for q in a_fresh])
            rng = np.random.default_rng(SEED)
            boot = [diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(10000)]
            res['fresh_direct_gain'] = round(float(diff.mean()), 4)
            res['fresh_gain_ci95'] = [round(float(x), 4) for x in np.percentile(boot, [2.5, 97.5])]
        report['methods'][label] = res
    write(OUT / 'report.json', report)
    print(json.dumps(report, indent=1))


if __name__ == '__main__':
    score() if '--score' in sys.argv else run()
