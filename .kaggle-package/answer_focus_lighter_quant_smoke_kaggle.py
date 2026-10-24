"""Self-contained Kaggle/GPU quantization smoke check for gte-reranker-modernbert-base and the two Ettin
reranker sizes (round 2 of docs/ANSWER_FOCUS_CHALLENGERS_PROTOCOL.md's successors). Scores a small fixed set
of smoke pairs in fp32, dynamically quantizes each model to int8, re-scores the same pairs, and reports
whether the scores agree within tolerance.

Why this matters: Apollos's (Nemotron's) FIRST int8 attempt had a real sign-flip bug from dynamic
quantization -- not a hypothetical risk, a bug that actually shipped and was caught, requiring a pivot to
weight-only quantization (see memory apollos-int8-fixed-weight-only). gte/Ettin are a different, generally
more quantization-friendly architecture (ModernBERT/BERT-family, not a Llama-style decoder), so dynamic
quantization is the right thing to try FIRST here -- but "generally friendlier" is an expectation, not a
guarantee, and this script's whole job is checking that expectation against real numbers rather than
assuming it.

NOT using optimum.onnxruntime, by design: confirmed on Kaggle 2026-10-23 that optimum-onnx 0.1.0 requires
`transformers<4.58.0`, while Ettin's tokenizer requires `transformers>=5.0` (TokenizersBackend did not exist
before v5) -- these two cannot both be satisfied in one environment, so optimum's ORTModelForSequenceClassification
/ORTQuantizer path is unusable here for Ettin specifically. Instead this exports via plain torch.onnx.export
(same pattern tool/export_onnx.py already uses in this repo) and quantizes via onnxruntime.quantization's
quantize_dynamic directly -- neither needs optimum at all, so this works under transformers>=5.0 throughout
(gte doesn't strictly need >=5.0, but using the same path for all three models keeps this script simple and
is harmless for gte).

Upload as a Kaggle Notebook with the SAME 'challengers' dataset Task 2's script used attached
  (/kaggle/input/<dataset>/content.db, catalog.db, test-queries/*.json)
Turn on a GPU accelerator. Paste this whole file into a cell, set ACTION near the bottom to 'gte', 'ettin150'
or 'ettin400', run the cell (repeat for each model -- output persists across cell runs in the same session).

REQUIRED SETUP CELL, every time the kernel starts or restarts (pip installs do NOT survive a kernel restart
on Kaggle -- only files already written to /kaggle/working/ do, so this must be re-run after every restart):
  !pip install -q -U "transformers>=5.0"
No optimum install needed at all for this script.

Download /kaggle/working/quant-smoke/<model>.json for each model afterward (the project's existing
zip_working_output.py pattern works here too -- point it at the quant-smoke folder instead).
"""
ACTION = 'gte'  # <-- SET THIS FIRST: 'gte', 'ettin150', or 'ettin400' -- then run the whole cell

import bisect
import json
import sqlite3
import sys
from pathlib import Path

IN = Path('/kaggle/input')
_match = next(IN.rglob('content.db'), None) if IN.exists() else None
DATA = _match.parent if _match else Path('data')
print(f'DATA resolved to: {DATA} (exists: {DATA.exists()})', flush=True)
OUT = Path('/kaggle/working/quant-smoke') if Path('/kaggle/working').exists() else Path('.out/quant-smoke')
OUT.mkdir(parents=True, exist_ok=True)

MODELS = {
    'gte': ('Alibaba-NLP/gte-reranker-modernbert-base', 'f7481e6055501a30fb19d090657df9ec1f79ab2c'),
    'ettin150': ('cross-encoder/ettin-reranker-150m-v1', '025501c4e0f9bbeb4c5b198318e0089ff061cc14'),
    'ettin400': ('cross-encoder/ettin-reranker-400m-v1', '5dca36282a5d85f368d2544002513a29159b4c9e'),
}

# The scripture-domain pair: test-cup's query, paired with its highest- and lowest-scoring candidate verses
# from round 2's own gte run (verse 25445 scored 0.959 -- genuinely the top candidate for this query in
# round 1's source data too; verse 38783 scored 0.566 -- the weakest of its 200 candidates). Pulled from
# already-completed data, not authored fresh, per the plan's instruction.
SCRIPTURE_QUERY = 'What did Jesus say about cleaning the outside of a cup while leaving its inside unclean?'
RELEVANT_VERSE_ID = 25445
IRRELEVANT_VERSE_ID = 38783


class Corpus:
    def __init__(self):
        cat = sqlite3.connect(f'file:{(DATA / "catalog.db").as_posix()}?mode=ro', uri=True)
        self.chapters = cat.execute('SELECT book_id, chapter, first_verse_id FROM chapters ORDER BY first_verse_id').fetchall()
        self.firsts = [c[2] for c in self.chapters]
        self.db = sqlite3.connect(f'file:{(DATA / "content.db").as_posix()}?mode=ro', uri=True)

    def text(self, v, lang='english'):
        return self.db.execute(f'SELECT text FROM text_{lang} WHERE verse_id=?', (v,)).fetchone()[0]


def smoke_pairs():
    corpus = Corpus()
    return [
        ('What is the capital of France?', 'Paris is the capital of France.'),
        ('What is the capital of France?', 'Water freezes at zero degrees Celsius.'),
        (SCRIPTURE_QUERY, corpus.text(RELEVANT_VERSE_ID)),
        (SCRIPTURE_QUERY, corpus.text(IRRELEVANT_VERSE_ID)),
    ]


def score_fp32(name, pairs):
    import sentence_transformers
    from huggingface_hub import snapshot_download
    repo, revision = MODELS[name]
    folder = Path(snapshot_download(repo, revision=revision,
        allow_patterns=['*.json', '*.safetensors', '*.py', 'README.md', 'LICENSE*', '*.txt']))
    ce = sentence_transformers.CrossEncoder(str(folder), max_length=512, device='cuda', local_files_only=True)
    return [float(s) for s in ce.predict(pairs, convert_to_numpy=True)], folder


def export_onnx(name, folder, pairs):
    """Manual torch.onnx.export -- no optimum, same pattern tool/export_onnx.py already uses in this repo.
    Traces with one real pair from `pairs` so dynamic axes cover realistic shapes, same spirit as
    export_onnx.py tracing with real example sentences rather than a dummy fixed-size input."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    model = AutoModelForSequenceClassification.from_pretrained(folder, local_files_only=True).eval()
    tokenizer = AutoTokenizer.from_pretrained(folder, local_files_only=True)
    query, text = pairs[0]
    example = tokenizer(query, text, return_tensors='pt', truncation=True, max_length=512)
    onnx_dir = OUT / 'onnx-export' / name
    onnx_dir.mkdir(parents=True, exist_ok=True)
    fp32_path = onnx_dir / 'model_fp32.onnx'
    prog = torch.onnx.export(
        model, (example['input_ids'], example['attention_mask']), dynamo=True,
        input_names=['input_ids', 'attention_mask'], output_names=['logits'],
        dynamic_shapes={'input_ids': {0: 'batch', 1: 'seq'}, 'attention_mask': {0: 'batch', 1: 'seq'}})
    prog.save(str(fp32_path))
    return fp32_path, tokenizer


def score_int8(name, folder, pairs):
    import onnxruntime as ort
    from onnxruntime.quantization import QuantType, quantize_dynamic
    fp32_path, tokenizer = export_onnx(name, folder, pairs)
    int8_path = fp32_path.with_name('model_int8.onnx')
    quantize_dynamic(str(fp32_path), str(int8_path), weight_type=QuantType.QInt8)
    sess = ort.InferenceSession(str(int8_path), providers=['CPUExecutionProvider'])
    scores = []
    for query, text in pairs:
        inputs = tokenizer(query, text, return_tensors='np', truncation=True, max_length=512)
        logits = sess.run(['logits'], {'input_ids': inputs['input_ids'], 'attention_mask': inputs['attention_mask']})[0]
        scores.append(float(logits.reshape(-1)[0]))
    return scores


def run(name):
    assert DATA.exists(), f'Expected dataset at {DATA} -- attach the same challengers dataset Task 2 used'
    pairs = smoke_pairs()
    fp32_scores, folder = score_fp32(name, pairs)
    print(f'{name} fp32 scores: {fp32_scores}', flush=True)
    int8_scores = score_int8(name, folder, pairs)
    print(f'{name} int8 scores: {int8_scores}', flush=True)
    max_abs_diff = max(abs(a - b) for a, b in zip(fp32_scores, int8_scores))
    within_tolerance = max_abs_diff < 0.05  # same tolerance class as Apollos's own weight-only verification
    result = {'model': name, 'pairs': [{'query': q, 'text': t} for q, t in pairs],
        'fp32_scores': fp32_scores, 'int8_scores': int8_scores,
        'max_abs_diff': max_abs_diff, 'within_tolerance': within_tolerance}
    (OUT / f'{name}.json').write_text(json.dumps(result, ensure_ascii=False, indent=1), 'utf-8')
    print(f'{name}: max_abs_diff={max_abs_diff:.4f} within_tolerance={within_tolerance}', flush=True)


def main():
    if len(sys.argv) == 2 and sys.argv[1] in MODELS:
        run(sys.argv[1])
    else:
        run(ACTION)


if __name__ == '__main__':
    main()
