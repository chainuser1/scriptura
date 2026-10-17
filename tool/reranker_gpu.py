"""Answer focus on the graphics chip (DirectML), fp16. Runs in a separate venv with onnxruntime-directml:

  python -m venv local-benchmarks/dml-venv
  local-benchmarks/dml-venv/Scripts/pip install onnxruntime-directml transformers numpy onnx
  local-benchmarks/dml-venv/Scripts/python.exe -I tool/reranker_gpu.py

fp16 model: made from local-benchmarks/reranker-speed/fp32 (weights fp16, inputs and logits fp32). Adds runs
'dml_fp16_k{30,15,10}' to local-benchmarks/reranker-speed/runs.json, then refreshes the blind sheet of ungraded passages.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
from reranker_speed import KS, OUT, STAGE2, THREADS, sheet
from reranker_stage2 import TOP, Corpus, read, write


def fp16_model():
    path = OUT / 'fp16/model.onnx'
    if not path.exists():
        import onnx
        from onnxruntime.transformers.float16 import convert_float_to_float16
        model = onnx.load(str(OUT / 'fp32/model.onnx'))
        half = convert_float_to_float16(model, keep_io_types=True, disable_shape_infer=True)  # the fp32 graph is over the 2 GB proto limit
        path.parent.mkdir(parents=True, exist_ok=True)
        onnx.save(half, str(path))  # about 1.1 GB: one file
    return path


def main():
    import onnxruntime as ort
    from transformers import AutoTokenizer
    assert 'DmlExecutionProvider' in ort.get_available_providers(), ort.get_available_providers()
    tok = AutoTokenizer.from_pretrained(OUT / 'tokenizer')
    so = ort.SessionOptions()
    so.intra_op_num_threads, so.inter_op_num_threads = THREADS, 1
    so.enable_mem_pattern = False  # required by DirectML
    sess = ort.InferenceSession(str(fp16_model()), so, providers=['DmlExecutionProvider', 'CPUExecutionProvider'])
    assert sess.get_providers()[0] == 'DmlExecutionProvider', sess.get_providers()
    corpus = Corpus()
    rows = [r for r in read(STAGE2 / 'rankings.json')['rankings'] if r['candidates'] and r['kind'] != 'absent']

    def score(q, texts):
        x = tok([[q, t] for t in texts], padding=True, truncation=True, max_length=512, return_tensors='np')
        return sess.run(None, {'input_ids': x['input_ids'].astype(np.int64), 'attention_mask': x['attention_mask'].astype(np.int64)})[0].reshape(-1).tolist()

    data = read(OUT / 'runs.json')
    data['sizes_mb']['onnx_fp16'] = (OUT / 'fp16/model.onnx').stat().st_size / 2**20
    for k in KS:
        score(rows[0]['query'], [corpus.text(v, rows[0]['language']) for v in rows[0]['candidates'][:k]])  # warm
        times, tops = [], {}
        for r in rows:
            cands = r['candidates'][:k]
            t = time.perf_counter()
            s = score(r['query'], [corpus.text(v, r['language']) for v in cands])
            times.append(time.perf_counter() - t)
            tops[r['id']] = [v for _, _, v in sorted((-x, i, v) for i, (v, x) in enumerate(zip(cands, s)))][:TOP]
        data['runs'][f'dml_fp16_k{k}'] = {'median_s': float(np.median(times)), 'p90_s': float(np.percentile(times, 90)), 'top5': tops}
        print(f'dml_fp16_k{k}', round(float(np.median(times)), 2), 's median', flush=True)
    write(OUT / 'runs.json', data)
    sheet(rows, data, corpus)


if __name__ == '__main__':
    main()
