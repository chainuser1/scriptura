"""Does the engine surface what the user is TRYING to do (compare, define, tell a story, find a person...)?

The genome's predicted vector for a query already carries intent in its structural dimensions (A24 definition,
A25 comparison, A15 narrative, ...). This evaluates ways to use that, using only data we already ship:

  struct / topic subspaces   cosine over structural families (form, voice, structure, epistemic, relation, ...)
                             and over topical families (doctrine, salvation, divine, emotion, condition, ...)
  concept-by-concept (A vs B) a soft-AND over the two concepts scored separately, so a verse must relate to BOTH
  entity linking (people)     legacy AI people index (quarantined, quality unreviewed) to separate same-name people

Everything is computed on the same candidate union as Experiment D, with the INT8 query encoder.

  .venv\\Scripts\\python.exe -I tool/intent_eval.py [--show 3]
"""
import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

import numpy as np
from scipy import sparse as sp
from transformers import AutoTokenizer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from demo_queries import Entities as LegacyEntities  # noqa: E402
from entity_linker import PeopleIndex  # noqa: E402


class Entities(PeopleIndex):
    """Gated linker (tool/entity_linker.py) in the (status, [(entity, score)]) shape this script uses."""

    def link(self, query):
        r = super().link(query)
        status = 'single' if r['filter'] else ('none' if r['status'] in ('generic', 'none') else r['status'])
        return status, [(e, 0) for e in r['candidates']]
from eval_quantized import Pack, variant_path  # noqa: E402
from quantize_onnx import encode, session  # noqa: E402
from reference_search import DEFAULT_EXTRACTED, VOCAB, Searcher, normalize_rows, top_rows, zscore  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RELEASE = ROOT / 'generated-artifacts' / 'release'
STRUCT_FAMILIES, TOPIC_FAMILIES = set('ABGIJKLTV'), set('CDEFPRS')
STRUCT_DIMS = ('A25_form_comparison_contrast_pair', 'J05_structure_contrast_counterpoint', 'G01_moral_binary_contrast')


class World:
    def __init__(self, variant='int8_matmul'):
        self.s = Searcher(DEFAULT_EXTRACTED, encoder=object())
        with np.load(DEFAULT_EXTRACTED / 'scripture-genome-question-hidden4096-optimized' / 'head_fp16.npz', allow_pickle=False) as z:
            self.s.head = {'0.weight': z['w0'].astype(np.float32), '0.bias': z['b0'].astype(np.float32),
                           '2.weight': z['w1'].astype(np.float32), '2.bias': z['b1'].astype(np.float32)}
        bundle = DEFAULT_EXTRACTED / 'scripture-retrieval-english-v1'
        wg = np.load(bundle / 'weighted_genome_embeddings.f16.npy', allow_pickle=False).astype(np.float32)
        self.wg = normalize_rows(wg)
        genes = [l.strip() for l in (bundle / 'gene_ids.txt').read_text('utf-8').split('\n') if l.strip()]
        self.si = np.array([i for i, g in enumerate(genes) if g[0] in STRUCT_FAMILIES])
        self.ti = np.array([i for i, g in enumerate(genes) if g[0] in TOPIC_FAMILIES])
        self.Vs, self.Vt = normalize_rows(self.wg[:, self.si]), normalize_rows(self.wg[:, self.ti])
        raw = np.load(bundle / 'genome_vectors.f16.npy', allow_pickle=False).astype(np.float32)
        self.cmp_flag = raw[:, [genes.index(d) for d in STRUCT_DIMS]].mean(axis=1)   # stored 'is a comparison/contrast verse'
        self.tok = AutoTokenizer.from_pretrained(DEFAULT_EXTRACTED / 'bge-m3-pinned')
        self.unused = {self.tok.cls_token_id, self.tok.eos_token_id, self.tok.pad_token_id, self.tok.unk_token_id}
        self.pack, self.sess = Pack(), session(variant_path(variant))
        self.vids = self.s.verse_ids
        self.row_of = {int(v): i for i, v in enumerate(self.vids)}
        c = sqlite3.connect(f'file:{(RELEASE / "content.db").as_posix()}?mode=ro', uri=True)
        self.text = dict(c.execute('SELECT verse_id, text FROM text_english'))
        cat = sqlite3.connect(f'file:{(RELEASE / "catalog.db").as_posix()}?mode=ro', uri=True)
        import bisect
        self._chap = cat.execute('SELECT book_id, chapter, first_verse_id FROM chapters ORDER BY first_verse_id').fetchall()
        self._firsts = [x[2] for x in self._chap]
        self._names = dict(cat.execute('SELECT book_id, name FROM book_names_english'))
        self._bisect = bisect.bisect_right
        self.entities = Entities()

    def ref(self, v):
        bid, ch, lo = self._chap[self._bisect(self._firsts, v) - 1]
        return f'{self._names[bid]} {ch}:{v - lo + 1}'

    def encode(self, texts):
        return encode(self.sess, self.tok, texts, self.unused, batch=1)

    def full_signals(self, dense, sparse_w):
        s = self.s
        gw = normalize_rows((s.genome_of(dense) * s.sw)[None, :])[0]
        qs = sp.lil_matrix((1, VOCAB), dtype=np.float32)
        for t, x in sparse_w.items():
            qs[0, t] = x
        return {'da': (s.dense @ dense).astype(np.float64), 'sa': (s.csr @ qs.tocsr().T).toarray().ravel().astype(np.float64),
                'ga': (self.wg @ gw).astype(np.float64),
                'gs': (self.Vs @ (gw[self.si] / max(np.linalg.norm(gw[self.si]), 1e-12))).astype(np.float64),
                'gt': (self.Vt @ (gw[self.ti] / max(np.linalg.norm(gw[self.ti]), 1e-12))).astype(np.float64)}


CMP_PATTERNS = [
    re.compile(r'^(?:what (?:is|are) )?the differences? between (?:the )?(.+?) and (?:the )?(.+?)\??$', re.I),
    re.compile(r'^how (?:are|is|do) (?:the )?(.+?) and (?:the )?(.+?) (?:different|differ|related|similar).*$', re.I),
    re.compile(r'^compare (?:the )?(.+?) (?:and|with|to) (?:the )?(.+?)\??$', re.I),
    re.compile(r'^(?:is it )?(?:better|greater|more important)(?: to have)? (.+?) or (?:to )?(.+?)\??$', re.I),
    re.compile(r'^(.+?)\s+(?:vs\.?|versus)\s+(.+?)\??$', re.I),
    re.compile(r'^(.+?)\s+or\s+(.+?)\??$', re.I),
]


def parse_comparison(q):
    q = q.strip()
    for p in CMP_PATTERNS:
        m = p.match(q)
        if m:
            clean = lambda s: re.sub(r'\b(for sure|the|a|an)\b', ' ', re.sub(r'^(to have|to be|to)\s+', '', s.strip(), flags=re.I), flags=re.I).strip(' ?.')  # noqa: E731
            a, b = clean(m.group(1)), clean(m.group(2))
            if a and b and a.lower() != b.lower():
                return [a, b]
    return None


def is_person_question(q):
    return bool(re.match(r'^who\s+(?:is|was|were)\b', q.strip(), re.I))


def analyze(w, query):
    dense, sparse, col, _ = w.encode([query])
    F = w.full_signals(dense[0], sparse[0])
    comp = parse_comparison(query)
    concept = []
    if comp:
        for c in comp:
            d2, s2, _c, _ = w.encode([c])
            concept.append(w.full_signals(d2[0], s2[0]))
    lanes = [F['da'], F['sa'], F['ga']] + [x[k] for x in concept for k in ('da', 'ga')]
    cand = np.unique(np.concatenate([top_rows(x, w.vids, 200 if i < 3 else 100) for i, x in enumerate(lanes)]))
    A = {'ids': w.vids[cand], 'rows': cand, 'comp': comp, 'F': F,
         'ca': w.pack.maxsim(col[0], cand), 'r9010': w.vids[top_rows(0.9 * zscore(F['ga']) + 0.1 * zscore(F['da']), w.vids, 20)]}
    A['Z'] = np.stack([zscore(F['da'][cand]), zscore(F['sa'][cand]), zscore(A['ca']), zscore(F['ga'][cand]),
                       zscore(F['gs'][cand]), zscore(F['gt'][cand])])
    if concept:
        cov = []
        for x in concept:
            cov.append(0.5 * zscore(x['da'][cand]) + 0.2 * zscore(x['sa'][cand]) + 0.3 * zscore(x['ga'][cand]))
        A['cov'] = np.stack(cov)
    A['entity'] = w.entities.link(query) if is_person_question(query) else ('none', [])
    return A


# weights over (dense, sparse, colbert, genome_all, genome_struct, genome_topic)
FIXED = {
    'experiment_d': (0.28, 0.14, 0.28, 0.30, 0, 0),
    'lean g80': (0.10, 0.10, 0.0, 0.80, 0, 0),
    'full g80+colbert': (0.05, 0.0, 0.15, 0.80, 0, 0),
    'lean split 40/20/20': (0.10, 0.10, 0.0, 0.40, 0.20, 0.20),
    'lean structure-heavy': (0.10, 0.10, 0.0, 0.30, 0.35, 0.15),
    'lean topic-heavy': (0.10, 0.10, 0.0, 0.30, 0.15, 0.35),
    'full split 40/20/20': (0.05, 0.0, 0.15, 0.40, 0.20, 0.20),
    'text lane (d.4 s.2 c.4)': (0.40, 0.20, 0.40, 0.0, 0, 0),
    'text no-ColBERT (d.6 s.4)': (0.60, 0.40, 0.0, 0.0, 0, 0),
    'balanced (d.15 s.10 c.25 g.50)': (0.15, 0.10, 0.25, 0.50, 0, 0),
    'genomic (s.1 c.2 g.7)': (0.0, 0.10, 0.20, 0.70, 0, 0),
    'balanced B2 (d.10 s.10 c.20 g.60)': (0.10, 0.10, 0.20, 0.60, 0, 0),
    'balanced no-ColBERT (d.25 s.15 g.60)': (0.25, 0.15, 0.0, 0.60, 0, 0),
}


def order(ids, score, k=20):
    return ids[np.lexsort((ids, -score))[:k]]


def rankers(w):
    out = {name: (lambda A, v=np.array(v): order(A['ids'], v @ A['Z'])) for name, v in FIXED.items()}
    out['90:10 (full-corpus)'] = lambda A: A['r9010']

    def cmp_and(A, mix=0.5, base='lean split 40/20/20'):
        sc = np.array(FIXED[base]) @ A['Z']
        if 'cov' in A:
            sc = (1 - mix) * zscore(sc) + mix * zscore(A['cov'].min(axis=0))   # soft-AND: must relate to BOTH concepts
        return order(A['ids'], sc)

    out['AND-concepts (50%)'] = cmp_and
    out['AND-concepts (75%)'] = lambda A: cmp_and(A, 0.75)
    out['AND + comparison-shaped'] = lambda A: order(
        A['ids'], 0.45 * zscore(np.array(FIXED['lean split 40/20/20']) @ A['Z']) +
        (0.40 * zscore(A['cov'].min(axis=0)) if 'cov' in A else 0) + 0.15 * zscore(w.cmp_flag[A['rows']]))

    def entity_aware(A, base='lean g80'):
        status, linked = A['entity']
        sc = np.array(FIXED[base]) @ A['Z']
        if status == 'single':
            eid = linked[0][0]
            mask = np.isin(A['ids'], np.array(w.entities.verses.get(eid, []), dtype=np.int64))
            if mask.any():
                sc = sc + 3.0 * mask          # entity's verses first, ordered by the engine's own score
        return order(A['ids'], sc)

    out['entity-aware lean'] = entity_aware
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--show', type=int, default=3, help='print top results for the first N comparison queries')
    a = ap.parse_args()
    tset = json.loads((ROOT / 'tool' / 'intent_test_set.json').read_text('utf-8'))
    w = World()
    R = rankers(w)
    hit = lambda ref, an: any(ref == x or (x.endswith(':*') and ref.startswith(x[:-1])) for x in an)  # noqa: E731
    stem = lambda t, terms: any(re.search(r'\b' + re.escape(x), t.lower()) for x in terms)  # noqa: E731
    names = list(R)
    table = {}

    # comparison
    print('=== COMPARISON  (both = top-10 verses mentioning BOTH concepts; one = only one; flag = stored comparison/contrast score)')
    rows = []
    for item in tset['comparison']:
        A = analyze(w, item['q'])
        res = {}
        for n in names:
            top = [int(x) for x in R[n](A)[:10]]
            terms = item['concepts']
            present = [[stem(w.text[v], t) for t in terms] for v in top]
            res[n] = (np.mean([all(p) for p in present]), np.mean([sum(p) == 1 for p in present]),
                      float(np.mean(w.cmp_flag[[w.row_of[v] for v in top]])))
        rows.append((item['q'], A['comp'], res, A))
        table.setdefault('comparison', []).append(res)
    print(f'parsed concepts: ' + '; '.join(f"{q!r} -> {c}" for q, c, _r, _A in rows))
    print(f'{"method":26s}{"both@10":>9s}{"one@10":>8s}{"flag":>8s}')
    for n in names:
        print(f'{n:26s}{np.mean([r[2][n][0] for r in rows]):9.2f}{np.mean([r[2][n][1] for r in rows]):8.2f}{np.mean([r[2][n][2] for r in rows]):8.3f}')
    for q, comp, res, A in rows[:a.show]:
        print(f'\n  "{q}"')
        for n in ('lean g80', 'full g80+colbert', 'AND + comparison-shaped'):
            print(f'    {n:26s} ' + ' | '.join(w.ref(int(v)) for v in R[n](A)[:8]))

    # anchored intents
    for intent, items in tset['anchored'].items():
        print(f'\n=== {intent.upper()}  (hit@5 / hit@10 / MRR@10 against anchor passages)')
        agg = {n: [] for n in names}
        for item in items:
            A = analyze(w, item['q'])
            for n in names:
                top = [w.ref(int(v)) for v in R[n](A)[:10]]
                first = next((i for i, r in enumerate(top) if hit(r, item['anchors'])), None)
                agg[n].append((float(first is not None and first < 5), float(first is not None), 0.0 if first is None else 1.0 / (first + 1)))
        print(f'{"method":26s}{"hit@5":>8s}{"hit@10":>8s}{"MRR":>8s}')
        for n in names:
            m = np.mean(agg[n], axis=0)
            print(f'{n:26s}{m[0]:8.2f}{m[1]:8.2f}{m[2]:8.2f}')
        table[intent] = agg

    # people
    print('\n=== PERSON  (share of top-10 verses that belong to the right person / to the same-name other person; legacy AI index as truth)')
    agg = {n: [] for n in names}
    link_log = []
    for item in tset['person']:
        A = analyze(w, item['q'])
        link_log.append((item['q'], A['entity'][0], [e for e, _ in A['entity'][1]][:2]))
        right = set(w.entities.verses.get(item['entity'], []))
        wrong = set(v for o in item['other'] for v in w.entities.verses.get(o, [])) - right
        for n in names:
            top = [int(v) for v in R[n](A)[:10]]
            agg[n].append((np.mean([v in right for v in top]), np.mean([v in wrong for v in top])))
    print('entity linking: ' + '; '.join(f'{q!r} -> {s} {e}' for q, s, e in link_log))
    print(f'{"method":26s}{"right@10":>10s}{"other@10":>10s}')
    for n in names:
        m = np.mean(agg[n], axis=0)
        print(f'{n:26s}{m[0]:10.2f}{m[1]:10.2f}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
