"""Offline, resumable Qwen/Nemotron comparison. No app imports or automatic grades.

python -I tool/answer_focus_challengers.py qwen|nemotron|review
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
import answer_focus_calibration_run as cal_run
import answer_focus_wide_pool as wide

OUT = ROOT / 'local-benchmarks/answer-focus-challengers'
SOURCE = ROOT / 'local-benchmarks/answer-focus-calibration'
MODELS = {
    'qwen': ('Qwen/Qwen3-Reranker-0.6B', 'e61197ed45024b0ed8a2d74b80b4d909f1255473'),
    'nemotron': ('nvidia/llama-nemotron-rerank-1b-v2', '828765652b05bd439c9789d2a6d093db1caa1443'),
}
INSTRUCTION = 'Given a web search query, retrieve relevant passages that answer the query'
PREFIX = '<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the Instruct provided. Note that the answer can only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
SUFFIX = '<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n'


def frozen(path, data):
    if path.exists():
        assert wide.read(path) == data, f'Input drift: {path}'
    else:
        wide.write(path, data)


def source_rows():
    rows = [wide.read(p) for p in sorted((SOURCE / 'queries/test').glob('*.json'))]
    assert len(rows) == 10 and len({r['id'] for r in rows}) == 10
    for r in rows:
        assert r['complete'] and len(r['candidates']) == len(set(r['candidates'])) == 200
        assert len(r['reranker']) == 200 and all(x is not None for x in r['reranker'])
    return rows


def order(scores):
    import math
    assert scores and all(x is not None and math.isfinite(x) for x in scores)
    return sorted(range(len(scores)), key=lambda i: (-scores[i], i))


class Scorer:
    def __init__(self, name):
        import torch
        import transformers
        from huggingface_hub import snapshot_download
        from transformers import AutoTokenizer, AutoModelForCausalLM, AutoModelForSequenceClassification
        self.torch, self.name = torch, name
        torch.set_num_threads(4)
        repo, revision = MODELS[name]
        print(f'Downloading/loading pinned {repo}', flush=True)
        folder = Path(snapshot_download(repo, revision=revision,
            allow_patterns=['*.json', '*.safetensors', '*.py', 'README.md', 'LICENSE*', '*.txt']))
        self.identity = {'repo': repo, 'revision': revision, 'torch': torch.__version__,
            'transformers': transformers.__version__, 'dtype': 'bfloat16', 'device': 'cpu',
            'threads': 4, 'batch_size': 1, 'max_length': 512,
            'files': {p.name: wide.digest(p) for p in sorted(folder.iterdir()) if p.is_file()}}
        self.tokenizer = AutoTokenizer.from_pretrained(folder, padding_side='left', local_files_only=True)
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        cls = AutoModelForCausalLM if name == 'qwen' else AutoModelForSequenceClassification
        self.model = cls.from_pretrained(folder, trust_remote_code=name == 'nemotron',
            local_files_only=True, torch_dtype=torch.bfloat16, low_cpu_mem_usage=True).eval()
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
        tensors = {'input_ids': torch.tensor([ids]), 'attention_mask': torch.ones((1, len(ids)), dtype=torch.long)}
        t = time.perf_counter()
        with torch.inference_mode():
            # Only the final Qwen position is needed; avoid allocating sequence x vocabulary logits.
            result = self.model(**tensors, **({'logits_to_keep': 1} if self.name == 'qwen' else {})).logits.float()
        score = float(result[0, -1, self.yes] - result[0, -1, self.no]) if self.name == 'qwen' else float(result.reshape(-1)[0])
        import math
        assert math.isfinite(score)
        return {'score': score, 'tokens_before_truncation': n, 'truncated': n > 512,
                'seconds': time.perf_counter()-t}


def run(name):
    rows, corpus = source_rows(), wide.Corpus()
    paths = [Path(__file__), ROOT/'docs/ANSWER_FOCUS_CHALLENGERS_PROTOCOL.md',
             ROOT/'tool/answer_focus_wide_pool.py', ROOT/'tool/reranker_stage2.py',
             SOURCE/'identity.json', wide.GEN/'release/content.db', wide.GEN/'release/catalog.db',
             *sorted((SOURCE/'queries/test').glob('*.json'))]
    frozen(OUT/'input-identity.json', {str(p.relative_to(ROOT)): wide.digest(p) for p in paths})
    for r in rows:
        texts = [corpus.text(v, r['language']) for v in r['candidates']]
        digest = hashlib.sha256(json.dumps(texts, ensure_ascii=False).encode()).hexdigest()
        assert digest == r['text_sha256'], 'Corpus changed since cached BGE scoring'
    scorer = Scorer(name)
    frozen(OUT/name/'identity.json', scorer.identity)
    smoke = [scorer.score('What is the capital of France?', t) for t in
             ('Paris is the capital of France.', 'Water freezes at zero degrees Celsius.')]
    assert smoke[0]['score'] > smoke[1]['score'], 'Runtime/template smoke check failed'
    wide.write(OUT/name/'smoke.json', smoke)
    print(f'{name} smoke passed; {sum(s["seconds"] for s in smoke):.1f}s for two pairs', flush=True)
    for r in rows:
        p = OUT/name/(r['id']+'.json')
        data = wide.read(p) if p.exists() else {'id': r['id'], 'candidates': r['candidates'], 'pairs': [], 'complete': False}
        assert data['id'] == r['id'] and data['candidates'] == r['candidates']
        for i in range(len(data['pairs']), 200):
            data['pairs'].append(scorer.score(r['query'], corpus.text(r['candidates'][i], r['language'])))
            wide.write(p, data)
            if (i+1) % 20 == 0:
                print(f'{name} {r["id"]} {i+1}/200', flush=True)
        data['complete'] = True
        wide.write(p, data)
    print(f'{name}: all 2,000 pairs complete', flush=True)


def review():
    corpus, items, sources = wide.Corpus(), {}, []
    for r in source_rows():
        methods = [list(range(5)), order(r['reranker'][:10])[:5], order(r['reranker'])[:5]]
        for name in MODELS:
            p = OUT/name/(r['id']+'.json')
            got = wide.read(p)
            assert got['complete'] and got['candidates'] == r['candidates']
            methods.append(order([x['score'] for x in got['pairs']])[:5])
            sources.append(p)
        for indices in methods:
            for i in indices:
                v = r['candidates'][i]
                key = f'{r["id"]}:{v}'
                items[key] = {'item': key, 'query': r['query'], 'reference': corpus.ref(v),
                    'context': [{'reference': corpus.ref(u), 'focal': u == v, 'text': text}
                                for u, text in corpus.window(v, r['language'])]}
    blind = sorted(items.values(), key=lambda x: hashlib.sha256(('challengers:'+x['item']).encode()).hexdigest())
    frozen(OUT/'blind-view.json', blind)
    frozen(OUT/'review-decisions.json', {'reviewer': '', 'review_type': '',
        'source_sha256': {str(p.relative_to(ROOT)): wide.digest(p) for p in
                         [OUT/'blind-view.json', OUT/'input-identity.json', *sources]},
        'items': [{'item': r['item'], 'grade': None, 'reason': ''} for r in blind]})
    print(f'{len(blind)} unique passages ready for blind review; no quality scores inferred.')


def report():
    """Fixed-slot P@5 (protocol: missing results count as zero) for the five frozen methods, on the 10 reused test
    questions. 8 are answerable, 2 (test-phone-model, test-rice-protein) are absent-answer controls, scored
    separately per protocol ("absent controls separately"). Requires review-decisions.json fully graded (no
    grade: None rows) -- exploratory/development-data result, not a claim on independent data (protocol line 14).
    """
    decisions = wide.read(OUT / 'review-decisions.json')
    ungraded = [r['item'] for r in decisions['items'] if r['grade'] is None]
    assert not ungraded, f'{len(ungraded)} ungraded passages remain: {ungraded[:5]}...'
    by_key = {}
    for r in decisions['items']:
        qid, v = r['item'].rsplit(':', 1)
        by_key[(qid, int(v))] = r['grade']

    def grade_fn(qid, v):
        return by_key.get((qid, v))

    method_names = ['compass_top5', 'answer_focus_today_bge10', 'bge_at200', 'qwen_at200', 'nemotron_at200']
    rows = source_rows()
    out = {'scope': 'Exploratory development data (10 reused calibration/test questions) -- not a claim on '
                    'independent held-out data, per docs/ANSWER_FOCUS_CHALLENGERS_PROTOCOL.md.',
           'methods': {name: {'answerable': [], 'absent': {}} for name in method_names}}
    for r in rows:
        indices = [list(range(5)), order(r['reranker'][:10])[:5], order(r['reranker'])[:5]]
        for name in MODELS:
            got = wide.read(OUT / name / (r['id'] + '.json'))
            indices.append(order([x['score'] for x in got['pairs']])[:5])
        answerable = r['kind'] != 'absent'
        for method_name, idx in zip(method_names, indices):
            displayed = [r['candidates'][i] for i in idx]
            scored = cal_run.score_method(r['id'], displayed, grade_fn)
            scored['question_id'] = r['id']
            # a false promotion: a graded non-answer (0) the method actually surfaced into its displayed top-5
            scored['false_promotions'] = sum(1 for v in displayed if grade_fn(r['id'], v) == 0)
            if answerable:
                out['methods'][method_name]['answerable'].append(scored)
            else:
                out['methods'][method_name]['absent'][r['id']] = scored['displayed']

    for name, m in out['methods'].items():
        rows_ = m['answerable']
        m['direct_p5_mean'] = round(sum(x['direct_p5'] for x in rows_) / len(rows_), 4)
        m['related_p5_mean'] = round(sum(x['related_p5'] for x in rows_) / len(rows_), 4)
        m['any_direct_rate'] = round(sum(x['any_direct'] for x in rows_) / len(rows_), 4)
        m['false_promotions'] = sum(x['false_promotions'] for x in rows_)
    out['source_sha256'] = {str(p.relative_to(ROOT)): wide.digest(p) for p in
                            [OUT / 'review-decisions.json', OUT / 'blind-view.json', Path(__file__)]}
    frozen(OUT / 'test-report.json', out)
    for name, m in out['methods'].items():
        print(f"{name:26s} direct_p5={m['direct_p5_mean']:.3f} related_p5={m['related_p5_mean']:.3f} "
              f"any_direct={m['any_direct_rate']:.3f} false_promotions={m['false_promotions']} "
              f"absent_counts={m['absent']}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=(*MODELS, 'review', 'report'))
    action = parser.parse_args().action
    {'review': review, 'report': report}.get(action, lambda: run(action))()
