"""Executable Experiment D reference (PLAN section 6): BGE-M3 dense + sparse + ColBERT + Scripture Genome.

Development tool only, not a shipping runtime. Independent reimplementation of the three BGE-M3 outputs from
the pinned base weights and projection files; `--selfcheck` diffs it against FlagEmbedding 1.4.2.

  python -I tool/reference_search.py "what is faith" [--top-k 20] [--out result.json]
  python -I tool/reference_search.py --queries-file q.txt --out golden.json
  python -I tool/reference_search.py --selfcheck [--out selfcheck.json]

Filtered search and empty/single-candidate behavior: docs/SEARCH_SPEC.md (Searcher.search allowed_verse_ids).
Run with the project venv so FlagEmbedding is importable for --selfcheck: .venv\\Scripts\\python.exe -I ...
"""
import argparse
import gc
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from scipy import sparse as sp
from scipy.special import erf
from transformers import AutoModel, AutoTokenizer

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EXTRACTED = ROOT / '.artifact-staging' / 'import-application-v1' / 'extracted'

SIGNAL_WEIGHTS = {'dense': 0.28, 'sparse': 0.14, 'colbert': 0.28, 'genome': 0.30}
FAMILY_WEIGHTS = {'B': 0.75, 'I': 0.50, 'N': 0.50, 'Q': 0.0, 'T': 0.75, 'U': 0.75}  # all others 1.0
LANE_K = 200
MAX_LEN = 512  # including special tokens
VOCAB = 250002

GOLDEN_QUERIES = [
    'What does the Bible teach about forgiveness?',
    'faith',
    'I feel anxious and afraid about the future',
    'In the beginning God created the heavens and the earth',
    '¿Qué dice la Biblia sobre el amor al prójimo?',
    'Ano ang sinasabi ng kasulatan tungkol sa pagpapakumbaba? 🙏',
]


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 22), b''):
            h.update(chunk)
    return h.hexdigest()


class Encoder:
    """BGE-M3 dense (normalized CLS), sparse (relu(linear) max-per-token), ColBERT (CLS dropped, normalized)."""

    def __init__(self, base_dir):
        base_dir = Path(base_dir)
        self.tok = AutoTokenizer.from_pretrained(base_dir)
        self.model = AutoModel.from_pretrained(base_dir, dtype=torch.float32).eval()
        self.sparse = torch.nn.Linear(1024, 1)
        self.sparse.load_state_dict(torch.load(base_dir / 'sparse_linear.pt', map_location='cpu', weights_only=True))
        self.colbert = torch.nn.Linear(1024, 1024)
        self.colbert.load_state_dict(torch.load(base_dir / 'colbert_linear.pt', map_location='cpu', weights_only=True))
        t = self.tok
        self.unused = {t.cls_token_id, t.eos_token_id, t.pad_token_id, t.unk_token_id}

    @torch.inference_mode()
    def encode(self, texts, batch=16):
        """-> list of (dense[1024] f32, {token_id: weight}, colbert[n-1,1024] f32), in input order."""
        enc = self.tok(list(texts), add_special_tokens=True, truncation=False)
        lens = [len(x) for x in enc['input_ids']]
        if min(lens) <= 2:
            raise ValueError('empty input')
        if max(lens) > MAX_LEN:
            raise ValueError(f'input has {max(lens)} tokens; reference limit is {MAX_LEN} including specials')
        out = [None] * len(lens)
        order = np.argsort(lens, kind='stable')
        for s in range(0, len(order), batch):
            idx = order[s:s + batch]
            b = self.tok.pad([{'input_ids': enc['input_ids'][i], 'attention_mask': enc['attention_mask'][i]} for i in idx],
                             return_tensors='pt')
            h = self.model(input_ids=b['input_ids'], attention_mask=b['attention_mask']).last_hidden_state
            dense = F.normalize(h[:, 0], dim=-1)
            tw = torch.relu(self.sparse(h)).squeeze(-1)
            col = F.normalize(self.colbert(h[:, 1:]) * b['attention_mask'][:, 1:, None], dim=-1)
            for j, i in enumerate(idx):
                n = int(b['attention_mask'][j].sum())
                w = {}
                for t, x in zip(b['input_ids'][j, :n].tolist(), tw[j, :n].tolist()):
                    if t not in self.unused and x > 0 and x > w.get(t, 0.0):
                        w[t] = x
                out[i] = (dense[j].numpy().copy(), w, col[j, :n - 1].numpy().copy())
        return out


def normalize_rows(m):
    return m / np.maximum(np.linalg.norm(m, axis=-1, keepdims=True), 1e-12)


def zscore(a):
    a = np.asarray(a, dtype=np.float64)
    if not np.isfinite(a).all():
        raise ValueError('non-finite score')
    if len(a) < 2:
        return np.zeros_like(a)
    sd = a.std(ddof=1)
    return np.zeros_like(a) if sd <= 1e-12 else (a - a.mean()) / sd


def top_rows(scores, verse_ids, k):
    """Row indices of top-k by score desc, ties by ascending canonical verse ID (deterministic)."""
    return np.lexsort((verse_ids, -scores))[:k]


class Searcher:
    def __init__(self, extracted=DEFAULT_EXTRACTED, encoder=None):
        self.ext = Path(extracted)
        r = self.ext / 'scripture-retrieval-english-v1'
        head_dir = self.ext / 'scripture-genome-question-hidden4096-full'
        self.encoder = encoder or Encoder(self.ext / 'bge-m3-pinned')
        self.verse_ids = np.load(r / 'verse_ids.npy', allow_pickle=False)
        self.dense = np.load(r / 'dense_embeddings.f16.npy', allow_pickle=False).astype(np.float32)
        genome = np.load(r / 'genome_vectors.f16.npy', allow_pickle=False).astype(np.float32)
        with np.load(r / 'sparse_index.csr.npz', allow_pickle=False) as z:
            self.csr = sp.csr_matrix((z['data'], z['indices'], z['indptr']), shape=tuple(int(x) for x in z['shape']))
        self.texts = [json.loads(l)['scripture_text'] for l in (r / 'scripture_text.jsonl').read_text('utf-8').splitlines()]
        self.gene_ids = [g for g in (r / 'gene_ids.txt').read_text('utf-8').split('\n') if g]
        self.sw = np.sqrt(np.array([FAMILY_WEIGHTS.get(g[0], 1.0) for g in self.gene_ids], dtype=np.float32))
        self.genome_w = normalize_rows(genome * self.sw)
        stored = np.load(r / 'weighted_genome_embeddings.f16.npy', allow_pickle=False).astype(np.float32)
        self.weighted_parity = float(np.abs(self.genome_w - stored).max())  # informational: sqrt(w) both sides
        with np.load(head_dir / 'head_fp32.npz', allow_pickle=False) as z:
            self.head = {k: z[k].astype(np.float32) for k in ('0.weight', '0.bias', '2.weight', '2.bias')}
        assert len(self.verse_ids) == len(self.texts) == self.dense.shape[0] == self.csr.shape[0] == genome.shape[0]

    def genome_of(self, dense_q):
        x = dense_q @ self.head['0.weight'].T + self.head['0.bias']
        x = 0.5 * x * (1.0 + erf(x / np.sqrt(2.0)))  # exact GELU
        x = x @ self.head['2.weight'].T + self.head['2.bias']
        return 1.0 / (1.0 + np.exp(-x))  # Sigmoid; 568 values, not probabilities

    def search(self, query, top_k=20, allowed_verse_ids=None):
        """allowed_verse_ids: None = whole corpus; else a filtered configuration (docs/SEARCH_SPEC.md).
        The engine is catalog-agnostic: book/chapter/canon filters are resolved to verse IDs by the caller."""
        t0 = time.perf_counter()
        rows = None
        if allowed_verse_ids is not None:
            ids = np.fromiter((int(v) for v in allowed_verse_ids), dtype=np.int64)
            rows = np.flatnonzero(np.isin(self.verse_ids, ids))
            if len(rows) == 0:  # nothing eligible: no model work, explicit status (not an error)
                return {'query': query, 'top_k': top_k, 'status': 'no_eligible_passages', 'eligible_passages': 0,
                        'candidates': 0, 'results': []}
        q_dense, q_sparse, q_col = self.encoder.encode([query])[0]
        t_enc = time.perf_counter()
        g = self.genome_of(q_dense)
        gw = normalize_rows((g * self.sw)[None, :])[0]
        sv = np.zeros(VOCAB, dtype=np.float32)
        for t, w in q_sparse.items():
            sv[t] = w
        s_dense = self.dense @ q_dense
        s_genome = self.genome_w @ gw
        s_sparse = self.csr @ sv
        t_scan = time.perf_counter()

        def lane(scores):  # filter applies BEFORE lane selection and standardization
            if rows is None:
                return top_rows(scores, self.verse_ids, LANE_K)
            return rows[top_rows(scores[rows], self.verse_ids[rows], LANE_K)]

        lanes = {n: lane(s) for n, s in (('dense', s_dense), ('sparse', s_sparse), ('genome', s_genome))}
        cand = np.unique(np.concatenate(list(lanes.values())))  # <= 600 rows
        cand = cand[np.argsort(self.verse_ids[cand], kind='stable')]
        passages = self.encoder.encode([self.texts[i] for i in cand])
        t_col = time.perf_counter()
        s_col = np.array([float((q_col @ p[2].T).max(axis=1).mean()) for p in passages], dtype=np.float64)

        raw = {'dense': s_dense[cand], 'sparse': s_sparse[cand], 'colbert': s_col, 'genome': s_genome[cand]}
        z = {k: zscore(v) for k, v in raw.items()}
        final = sum(SIGNAL_WEIGHTS[k] * z[k] for k in SIGNAL_WEIGHTS)
        order = top_rows(final, self.verse_ids[cand], top_k)
        results = [{
            'rank': r + 1, 'verse_id': int(self.verse_ids[cand[o]]), 'score': float(final[o]),
            'signals': {k: float(raw[k][o]) for k in raw}, 'z': {k: float(z[k][o]) for k in z},
            'text': self.texts[cand[o]],
        } for r, o in enumerate(order)]
        return {
            'query': query, 'top_k': top_k, 'status': 'ok',
            'eligible_passages': int(len(self.verse_ids) if rows is None else len(rows)),
            'candidates': int(len(cand)),
            'lane_sizes': {k: int(len(v)) for k, v in lanes.items()},
            'sparse_query_tokens': len(q_sparse), 'colbert_query_tokens': int(q_col.shape[0]),
            'seconds': {'encode_query': t_enc - t0, 'scans': t_scan - t_enc, 'encode_candidates': t_col - t_scan,
                        'total': time.perf_counter() - t0},
            'results': results,
        }


def environment(ext):
    import platform
    import scipy
    ident = {'python': platform.python_version(), 'torch': torch.__version__, 'numpy': np.__version__, 'scipy': scipy.__version__}
    import transformers
    ident['transformers'] = transformers.__version__
    try:
        import importlib.metadata as md
        ident['FlagEmbedding'] = md.version('FlagEmbedding')
    except Exception:
        ident['FlagEmbedding'] = None
    base = json.loads((ext / 'bge-m3-pinned' / 'manifest.json').read_text('utf-8'))
    ident['base_revision'] = base['revision']
    ident['head_checkpoint_sha256'] = sha256(ext / 'scripture-genome-question-hidden4096-full' / 'best.pt')
    ident['gene_ids_sha256'] = sha256(ext / 'scripture-retrieval-english-v1' / 'gene_ids.txt')
    ident['retrieval_config_sha256'] = sha256(ext / 'scripture-retrieval-english-v1' / 'retrieval_config.json')
    ident['signal_weights'] = SIGNAL_WEIGHTS
    ident['family_weights'] = FAMILY_WEIGHTS
    ident['lane_k'] = LANE_K
    return ident


def selfcheck(ext):
    """Mine vs FlagEmbedding 1.4.2 on golden queries. Loads one model at a time (7 GB dev machine)."""
    base = ext / 'bge-m3-pinned'
    enc = Encoder(base)
    mine = enc.encode(GOLDEN_QUERIES)
    del enc
    gc.collect()
    from FlagEmbedding import BGEM3FlagModel
    ref = BGEM3FlagModel(str(base), use_fp16=False, devices='cpu')
    o = ref.encode(GOLDEN_QUERIES, return_dense=True, return_sparse=True, return_colbert_vecs=True, max_length=MAX_LEN)
    rows, ok = [], True
    for i, q in enumerate(GOLDEN_QUERIES):
        d, w, c = mine[i]
        rd = np.asarray(o['dense_vecs'][i], dtype=np.float32)
        rw = {int(k): float(v) for k, v in o['lexical_weights'][i].items()}
        rc = np.asarray(o['colbert_vecs'][i], dtype=np.float32)
        row = {
            'query': q,
            'dense_cosine': float(d @ rd / (np.linalg.norm(d) * np.linalg.norm(rd))),
            'sparse_same_tokens': set(w) == set(rw),
            'sparse_max_abs': max((abs(w[k] - rw[k]) for k in w if k in rw), default=0.0),
            'colbert_same_shape': tuple(c.shape) == tuple(rc.shape),
            'colbert_max_abs': float(np.abs(c - rc).max()) if c.shape == rc.shape else None,
        }
        row['pass'] = (row['dense_cosine'] >= 0.9999 and row['sparse_same_tokens'] and row['sparse_max_abs'] < 1e-3
                       and row['colbert_same_shape'] and row['colbert_max_abs'] is not None and row['colbert_max_abs'] < 1e-3)
        ok &= row['pass']
        rows.append(row)
        print(('PASS ' if row['pass'] else 'FAIL ') + json.dumps(row, ensure_ascii=False))
    return ok, rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('queries', nargs='*')
    ap.add_argument('--queries-file')
    ap.add_argument('--top-k', type=int, default=20)
    ap.add_argument('--extracted', default=str(DEFAULT_EXTRACTED))
    ap.add_argument('--out')
    ap.add_argument('--selfcheck', action='store_true')
    ap.add_argument('--with-text', action='store_true', help='include passage text in --out (default: IDs and scores only)')
    a = ap.parse_args()
    ext = Path(a.extracted)

    if a.selfcheck:
        ok, rows = selfcheck(ext)
        if a.out:
            Path(a.out).write_text(json.dumps({'environment': environment(ext), 'selfcheck': rows, 'pass': ok},
                                              ensure_ascii=False, indent=2), 'utf-8')
        print('SELFCHECK', 'PASSED' if ok else 'FAILED')
        return 0 if ok else 1

    queries = list(a.queries)
    if a.queries_file:
        # utf-8-sig: Windows PowerShell 5.1 writes a BOM that would otherwise become part of query 1
        queries += [l.strip() for l in Path(a.queries_file).read_text('utf-8-sig').splitlines() if l.strip()]
    if not queries:
        ap.error('give a query, --queries-file, or --selfcheck')
    s = Searcher(ext)
    print(f'weighted-genome parity vs stored f16 (sqrt(w) both sides): max abs diff {s.weighted_parity:.2e}', file=sys.stderr)
    runs = [s.search(q, a.top_k) for q in queries]
    for r in runs:
        print(f"\n# {r['query']}  (candidates={r['candidates']}, {r['seconds']['total']:.1f}s)")
        for x in r['results']:
            print(f"{x['rank']:>3}  {x['verse_id']:>6}  {x['score']:+.3f}  {x['text'][:110]}")
    if a.out:
        if not a.with_text:  # scripture edition text stays out of committed goldens (PLAN 12.3)
            for r in runs:
                for x in r['results']:
                    del x['text']
        Path(a.out).write_text(json.dumps({'environment': environment(ext), 'runs': runs}, ensure_ascii=False, indent=2), 'utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
