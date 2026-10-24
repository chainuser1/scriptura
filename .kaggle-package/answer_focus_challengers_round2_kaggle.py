ACTION = 'gte'  # <-- SET THIS FIRST: 'gte', 'ettin150', or 'ettin400' -- then run the whole cell

"""Self-contained Kaggle/GPU version of tool/answer_focus_challengers.py's round-2 models. Scores the same 10
test questions x 200 candidates with gte-reranker-modernbert-base and two Ettin reranker sizes, on GPU, with no
dependency on the main repo. Mirrors answer_focus_challengers_kaggle.py's structure exactly.

These three are plain cross-encoders (unlike Qwen/Nemotron's custom templates/logit extraction), scored via
sentence_transformers.CrossEncoder. Built specifically because Ettin's repos require transformers>=5.0 (a
tokenizer-backend redesign -- TokenizersBackend did not exist before v5), which this machine's local Python
environment did not have; Kaggle's own environment is expected to be current enough, and if it is not this
script's own import of sentence_transformers/transformers will fail immediately and visibly, before any
download, same fail-fast shape as the rest of this file.

Upload as a Kaggle Notebook with a Dataset attached containing:
  /kaggle/input/<dataset>/content.db
  /kaggle/input/<dataset>/catalog.db
  /kaggle/input/<dataset>/test-queries/*.json   (the 10 cached test rows, same schema as locally)

Turn on a GPU accelerator (T4 x1 is enough) before running. Output lands in /kaggle/working/gte/*.json,
/kaggle/working/ettin150/*.json, /kaggle/working/ettin400/*.json -- download the whole /kaggle/working folder
and drop gte/, ettin150/, ettin400/ into local-benchmarks/answer-focus-challengers-round2/ locally, then run:
  .venv/Scripts/python.exe -I tool/answer_focus_challengers.py review

REQUIRED SETUP CELL, every time the kernel starts or restarts (Kaggle's base image ships transformers
4.57.6, below Ettin's floor; pip installs do NOT survive a kernel restart -- only files already written to
/kaggle/working/ do, so this must be re-run after every restart, not just the first time):
  !pip install -q -U "transformers>=5.0"
Confirmed 2026-10-23: a restart without re-running this reverts to 4.57.6 and Ettin's AutoProcessor fails
with "Unrecognized processing class" / "Tokenizer class TokenizersBackend does not exist" -- the same root
cause documented for the local environment, just resurfacing on Kaggle after a restart. gte does not need
this (its repo works fine on 4.57.6 too), but running the pin before gte as well is harmless.

In a Kaggle notebook cell: paste this whole file, set ACTION = 'gte' near the bottom, run the cell; change
ACTION to 'ettin150' then 'ettin400' and re-run for each (output from earlier passes is kept -- /kaggle/working
persists across cell runs in the same session).
"""
import bisect
import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path

IN = Path('/kaggle/input')
_match = next(IN.rglob('content.db'), None) if IN.exists() else None
DATA = _match.parent if _match else Path('data')  # local dry-run fallback
print(f'DATA resolved to: {DATA} (exists: {DATA.exists()})', flush=True)
OUT = Path('/kaggle/working') if Path('/kaggle/working').exists() else Path('.out')

MODELS = {
    'gte': ('Alibaba-NLP/gte-reranker-modernbert-base', 'f7481e6055501a30fb19d090657df9ec1f79ab2c'),
    'ettin150': ('cross-encoder/ettin-reranker-150m-v1', '025501c4e0f9bbeb4c5b198318e0089ff061cc14'),
    'ettin400': ('cross-encoder/ettin-reranker-400m-v1', '5dca36282a5d85f368d2544002513a29159b4c9e'),
}


def read(p):
    return json.loads(Path(p).read_text('utf-8-sig'))


def write(p, value):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1, allow_nan=False), 'utf-8')
    tmp.replace(p)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Corpus:
    """Minimal reimplementation of tool/reranker_stage2.py's Corpus against the uploaded catalog.db/content.db."""
    def __init__(self):
        cat = sqlite3.connect(f'file:{(DATA / "catalog.db").as_posix()}?mode=ro', uri=True)
        self.chapters = cat.execute('SELECT book_id, chapter, first_verse_id FROM chapters ORDER BY first_verse_id').fetchall()
        self.firsts = [c[2] for c in self.chapters]
        self.names = dict(cat.execute('SELECT book_id, name FROM book_names_english'))
        self.db = sqlite3.connect(f'file:{(DATA / "content.db").as_posix()}?mode=ro', uri=True)
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


def source_rows():
    rows = [read(p) for p in sorted((DATA / 'test-queries').glob('*.json'))]
    assert len(rows) == 10 and len({r['id'] for r in rows}) == 10
    for r in rows:
        assert r['complete'] and len(r['candidates']) == len(set(r['candidates'])) == 200
        assert len(r['reranker']) == 200 and all(x is not None for x in r['reranker'])
    return rows


class Scorer:
    def __init__(self, name):
        import torch
        import sentence_transformers
        from huggingface_hub import snapshot_download
        self.name = name
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        repo, revision = MODELS[name]
        print(f'Downloading/loading pinned {repo} on {self.device}', flush=True)
        folder = Path(snapshot_download(repo, revision=revision,
            allow_patterns=['*.json', '*.safetensors', '*.py', 'README.md', 'LICENSE*', '*.txt']))
        self.identity = {'repo': repo, 'revision': revision,
            'sentence_transformers': sentence_transformers.__version__, 'dtype': 'float32', 'device': self.device,
            'batch_size': 1, 'max_length': 512,
            'files': {p.name: digest(p) for p in sorted(folder.iterdir()) if p.is_file()}}
        self.cross_encoder = sentence_transformers.CrossEncoder(str(folder), max_length=512, device=self.device,
            local_files_only=True)
        self.tokenizer = self.cross_encoder.tokenizer

    def score(self, query, text):
        n = len(self.tokenizer.encode(query, text, truncation=True, max_length=512))
        t = time.perf_counter()
        score = float(self.cross_encoder.predict([(query, text)], convert_to_numpy=True)[0])
        import math
        assert math.isfinite(score)
        return {'score': score, 'tokens_before_truncation': n, 'truncated': n >= 512,
                'seconds': time.perf_counter() - t}


def run(name):
    assert DATA.exists(), f'Expected dataset at {DATA} -- attach the Kaggle dataset with content.db/catalog.db/test-queries'
    if name in ('ettin150', 'ettin400'):
        import transformers
        from packaging.version import Version
        v = Version(transformers.__version__)
        assert v >= Version('5.0'), (
            f'transformers {transformers.__version__} < 5.0 -- Ettin needs >=5.0. Re-run '
            f'`pip install -U "transformers>=5.0"` in a setup cell (pip installs do not survive a kernel '
            f'restart on Kaggle, so this must be re-run after every restart, not just once).')
    rows, corpus = source_rows(), Corpus()
    for r in rows:
        texts = [corpus.text(v, r['language']) for v in r['candidates']]
        digest_now = hashlib.sha256(json.dumps(texts, ensure_ascii=False).encode()).hexdigest()
        assert digest_now == r['text_sha256'], f'{r["id"]}: corpus text does not match the local BGE-scored cache'
    scorer = Scorer(name)
    write(OUT / name / 'identity.json', scorer.identity)
    smoke = [scorer.score('What is the capital of France?', t) for t in
             ('Paris is the capital of France.', 'Water freezes at zero degrees Celsius.')]
    assert smoke[0]['score'] > smoke[1]['score'], 'Runtime/template smoke check failed'
    write(OUT / name / 'smoke.json', smoke)
    print(f'{name} smoke passed; {sum(s["seconds"] for s in smoke):.1f}s for two pairs', flush=True)
    for r in rows:
        p = OUT / name / (r['id'] + '.json')
        data = read(p) if p.exists() else {'id': r['id'], 'candidates': r['candidates'], 'pairs': [], 'complete': False}
        assert data['id'] == r['id'] and data['candidates'] == r['candidates']
        for i in range(len(data['pairs']), 200):
            data['pairs'].append(scorer.score(r['query'], corpus.text(r['candidates'][i], r['language'])))
            write(p, data)
            if (i + 1) % 20 == 0:
                print(f'{name} {r["id"]} {i + 1}/200', flush=True)
        data['complete'] = True
        write(p, data)
    print(f'{name}: all 2,000 pairs complete', flush=True)


def main():
    # argparse is unreliable inside a Kaggle notebook kernel -- it injects its own sys.argv (a kernel
    # connection-file path), which argparse tries and fails to parse as our 'action' positional. Read the
    # action from the command line only when this file is actually invoked as a standalone script.
    if len(sys.argv) == 2 and sys.argv[1] in MODELS:
        run(sys.argv[1])
    else:
        run(ACTION)


if __name__ == '__main__':
    main()
