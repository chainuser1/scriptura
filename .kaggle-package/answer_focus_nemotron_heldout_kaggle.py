"""Self-contained Kaggle/GPU version for docs/ANSWER_FOCUS_NEMOTRON_HELDOUT_PROTOCOL.md: scores the 26 fresh
held-out questions x 200 candidates with Qwen3-Reranker-0.6B and the Nemotron reranker, on GPU, with no
dependency on the main repo. This confirms (or disconfirms) the challengers round's Nemotron result on
questions that round never saw.

Upload as a Kaggle Notebook with a Dataset attached containing:
  /kaggle/input/<dataset>/content.db
  /kaggle/input/<dataset>/catalog.db
  /kaggle/input/<dataset>/held-out-queries/*.json   (the 26 cached held-out rows, same schema as locally)

Turn on a GPU accelerator (T4 x1 is enough) before running. Output lands in /kaggle/working/qwen/*.json and
/kaggle/working/nemotron/*.json -- download the whole /kaggle/working folder and drop qwen/ and nemotron/ into
local-benchmarks/answer-focus-nemotron-heldout/ locally, then run:
  .venv/Scripts/python.exe -I tool/answer_focus_nemotron_heldout_review.py review

In a Kaggle notebook cell: paste this whole file, set ACTION = 'qwen' near the bottom, run the cell; when it
finishes, change ACTION = 'nemotron' and run the cell again (output from the first pass is kept -- /kaggle/working
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
# Kaggle's mount depth under /kaggle/input varies (flat <dataset-slug>/, or nested datasets/<user>/<slug>/
# depending on how the dataset was attached), so search recursively for the file that marks the data root
# instead of assuming a fixed depth.
_match = next(IN.rglob('content.db'), None) if IN.exists() else None
DATA = _match.parent if _match else Path('data')  # local dry-run fallback
print(f'DATA resolved to: {DATA} (exists: {DATA.exists()})', flush=True)
OUT = Path('/kaggle/working') if Path('/kaggle/working').exists() else Path('.out')

MODELS = {
    'qwen': ('Qwen/Qwen3-Reranker-0.6B', 'e61197ed45024b0ed8a2d74b80b4d909f1255473'),
    'nemotron': ('nvidia/llama-nemotron-rerank-1b-v2', '828765652b05bd439c9789d2a6d093db1caa1443'),
}
INSTRUCTION = 'Given a web search query, retrieve relevant passages that answer the query'
PREFIX = '<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the Instruct provided. Note that the answer can only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
SUFFIX = '<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n'


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
    rows = [read(p) for p in sorted((DATA / 'held-out-queries').glob('*.json'))]
    assert len(rows) == 26 and len({r['id'] for r in rows}) == 26
    for r in rows:
        assert r['complete'] and len(r['candidates']) == len(set(r['candidates'])) == 200
        assert len(r['reranker']) == 200 and all(x is not None for x in r['reranker'])
    return rows


class Scorer:
    def __init__(self, name):
        import torch
        import transformers
        from huggingface_hub import snapshot_download
        from transformers import AutoTokenizer, AutoModelForCausalLM, AutoModelForSequenceClassification
        self.torch, self.name = torch, name
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        repo, revision = MODELS[name]
        print(f'Downloading/loading pinned {repo} on {self.device}', flush=True)
        folder = Path(snapshot_download(repo, revision=revision,
            allow_patterns=['*.json', '*.safetensors', '*.py', 'README.md', 'LICENSE*', '*.txt']))
        self.identity = {'repo': repo, 'revision': revision, 'torch': torch.__version__,
            'transformers': transformers.__version__, 'dtype': 'bfloat16', 'device': self.device,
            'batch_size': 1, 'max_length': 512,
            'files': {p.name: digest(p) for p in sorted(folder.iterdir()) if p.is_file()}}
        self.tokenizer = AutoTokenizer.from_pretrained(folder, padding_side='left', local_files_only=True)
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        cls = AutoModelForCausalLM if name == 'qwen' else AutoModelForSequenceClassification
        self.model = cls.from_pretrained(folder, trust_remote_code=name == 'nemotron',
            local_files_only=True, torch_dtype=torch.bfloat16, low_cpu_mem_usage=True).eval().to(self.device)
        self.model.config.use_cache = False
        if self.model.config.pad_token_id is None:
            self.model.config.pad_token_id = self.tokenizer.pad_token_id
        if name == 'qwen':
            self.prefix = self.tokenizer.encode(PREFIX, add_special_tokens=False)
            self.suffix = self.tokenizer.encode(SUFFIX, add_special_tokens=False)
            self.yes = self.tokenizer.convert_tokens_to_ids('yes')
            self.no = self.tokenizer.convert_tokens_to_ids('no')
            assert self.yes != self.no

    def score(self, query, text):
        torch, tok = self.torch, self.tokenizer
        if self.name == 'qwen':
            body = tok.encode(f'<Instruct>: {INSTRUCTION}\n<Query>: {query}\n<Document>: {text}', add_special_tokens=False)
            n = len(self.prefix) + len(body) + len(self.suffix)
            ids = self.prefix + body[:512-len(self.prefix)-len(self.suffix)] + self.suffix
        else:
            ids = tok.encode(f'question:{query} \n \n passage:{text}')
            n = len(ids)
            ids = ids[:512]
        tensors = {'input_ids': torch.tensor([ids], device=self.device),
                   'attention_mask': torch.ones((1, len(ids)), dtype=torch.long, device=self.device)}
        t = time.perf_counter()
        with torch.inference_mode():
            result = self.model(**tensors, **({'logits_to_keep': 1} if self.name == 'qwen' else {})).logits.float()
        score = float(result[0, -1, self.yes] - result[0, -1, self.no]) if self.name == 'qwen' else float(result.reshape(-1)[0])
        import math
        assert math.isfinite(score)
        return {'score': score, 'tokens_before_truncation': n, 'truncated': n > 512,
                'seconds': time.perf_counter() - t}


def run(name):
    assert DATA.exists(), f'Expected dataset at {DATA} -- attach the Kaggle dataset with content.db/catalog.db/test-queries'
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
        run(ACTION)  # notebook cell: set ACTION = 'qwen' or 'nemotron' above and re-run this cell


ACTION = 'qwen'  # change to 'nemotron' for the second pass, then re-run this cell

if __name__ == '__main__':
    main()
