"""Self-contained Kaggle/GPU quantization smoke check for gte-reranker-modernbert-base and the two Ettin
reranker sizes (round 2 of docs/ANSWER_FOCUS_CHALLENGERS_PROTOCOL.md's successors). Scores a small fixed set
of smoke pairs in fp32, dynamically quantizes each model to int8 via optimum.onnxruntime, re-scores the same
pairs, and reports whether the scores agree within tolerance.

Why this matters: Apollos's (Nemotron's) FIRST int8 attempt had a real sign-flip bug from dynamic
quantization -- not a hypothetical risk, a bug that actually shipped and was caught, requiring a pivot to
weight-only quantization (see memory apollos-int8-fixed-weight-only). gte/Ettin are a different, generally
more quantization-friendly architecture (ModernBERT/BERT-family, not a Llama-style decoder), so dynamic
quantization is the right thing to try FIRST here -- but "generally friendlier" is an expectation, not a
guarantee, and this script's whole job is checking that expectation against real numbers rather than
assuming it.

Upload as a Kaggle Notebook with the SAME 'challengers' dataset Task 2's script used attached
  (/kaggle/input/<dataset>/content.db, catalog.db, test-queries/*.json)
Turn on a GPU accelerator. Paste this whole file into a cell, set ACTION near the bottom to 'gte', 'ettin150'
or 'ettin400', run the cell (repeat for each model -- output persists across cell runs in the same session).

REQUIRED SETUP CELL, every time the kernel starts or restarts (pip installs do NOT survive a kernel restart
on Kaggle -- only files already written to /kaggle/working/ do, so this must be re-run after every restart).
Install in TWO separate commands, OPTIMUM FIRST THEN TRANSFORMERS LAST, not one combined pin and not
transformers-first -- `pip install -U "transformers>=5.0" "optimum[onnxruntime]>=2.0"` together hits
ResolutionImpossible (confirmed on Kaggle 2026-10-23: optimum's onnxruntime extra has its own transformers
upper bound that conflicts with a loose >=5.0 in the same resolver pass), and installing transformers THEN
optimum risks optimum's own installer silently downgrading transformers back below 5.0 to satisfy its own
bound (the last `pip install` touching a shared dependency wins). Installing optimum first, then
transformers>=5.0 as the LAST command, makes transformers' pin the one that sticks:
  !pip install -q -U "optimum[onnxruntime]>=2.0"
  !pip install -q -U "transformers>=5.0"
The smoke check also re-verifies the live transformers.__version__ at runtime regardless (see
assert_transformers_ok() below) rather than trusting the install order alone.
Both pins matter and were each confirmed necessary: Ettin's repos need transformers>=5.0 (below that,
AutoProcessor fails with "Unrecognized processing class" / "TokenizersBackend does not exist"); an unpinned
`pip install optimum[onnxruntime]` can resolve to a pre-2.0 release whose ONNX export code still imports
transformers.file_utils.FLAX_WEIGHTS_NAME, which transformers v5 removed (v5 dropped TensorFlow/Flax support
entirely) -- that import fails with "cannot import name 'FLAX_WEIGHTS_NAME' from 'transformers.utils'" the
moment ORTModelForSequenceClassification is imported. optimum>=2.0 is the version line that supports
transformers v5.

Download /kaggle/working/quant-smoke/<model>.json for each model afterward (the project's existing
zip_working_output.py pattern works here too -- point it at the quant-smoke folder instead).
"""
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


def score_int8(folder, pairs):
    from optimum.onnxruntime import ORTModelForSequenceClassification, ORTQuantizer
    from optimum.onnxruntime.configuration import AutoQuantizationConfig
    from transformers import AutoTokenizer
    onnx_dir = OUT / 'onnx-export'
    onnx_dir.mkdir(exist_ok=True)
    model = ORTModelForSequenceClassification.from_pretrained(folder, export=True)
    tokenizer = AutoTokenizer.from_pretrained(folder)
    quantizer = ORTQuantizer.from_pretrained(model)
    qconfig = AutoQuantizationConfig.avx512_vnni(is_static=False, per_channel=False)  # dynamic quantization
    quantizer.quantize(save_dir=onnx_dir, quantization_config=qconfig)
    quantized = ORTModelForSequenceClassification.from_pretrained(onnx_dir, file_name='model_quantized.onnx')
    scores = []
    for query, text in pairs:
        inputs = tokenizer(query, text, return_tensors='pt', truncation=True, max_length=512)
        logits = quantized(**inputs).logits
        scores.append(float(logits.reshape(-1)[0]))
    return scores


def assert_transformers_ok():
    import transformers
    from packaging.version import Version
    v = Version(transformers.__version__)
    assert v >= Version('5.0'), (
        f'transformers {transformers.__version__} < 5.0 -- Ettin needs >=5.0. Re-run, in this exact order: '
        f'`pip install -U "optimum[onnxruntime]>=2.0"` THEN `pip install -U "transformers>=5.0"` last, so '
        f'the transformers pin is the one that sticks (optimum would otherwise downgrade it back).')


def run(name):
    assert DATA.exists(), f'Expected dataset at {DATA} -- attach the same challengers dataset Task 2 used'
    assert_transformers_ok()
    pairs = smoke_pairs()
    fp32_scores, folder = score_fp32(name, pairs)
    print(f'{name} fp32 scores: {fp32_scores}', flush=True)
    int8_scores = score_int8(folder, pairs)
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


ACTION = 'gte'  # change to 'ettin150' then 'ettin400' for the remaining passes, then re-run this cell

if __name__ == '__main__':
    main()
