"""Offline mathematical retrieval experiments; never imported by the application.

Run: .venv/Scripts/python.exe -I tool/mathematical_retrieval_experiment.py
Protocol: docs/MATHEMATICAL_RETRIEVAL_EXPERIMENT.md
Outputs (including private passage text) stay in local-benchmarks/.
"""
import argparse
import bisect
import ctypes
import hashlib
import html
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np
import scipy
from scipy import sparse
from scipy.special import erf, softmax
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
from volume_balance import balance, volume_of_rows

GEN = ROOT / 'generated-artifacts'
OUT = ROOT / 'local-benchmarks' / 'mathematical-retrieval-v1'
RAW = ROOT / '.artifact-staging/import-application-v1/extracted/scripture-retrieval-english-v1/genome_vectors.f16.npy'
CS = (0.01, 0.1, 1.0, 10.0)
ALPHAS = (0.0, 0.15, 0.5, 0.85)
BETAS = (0.0, 0.1, 0.3, 1.0)
SEED = 20261016


def read(path):
    return json.loads(Path(path).read_text('utf-8-sig'))


def write(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False), 'utf-8')


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(4 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def norm(x):
    return x / np.maximum(np.linalg.norm(x, axis=-1, keepdims=True), 1e-12)


def z(x):
    x = np.asarray(x, dtype=np.float64)
    assert np.isfinite(x).all()
    sd = x.std(ddof=1) if len(x) > 1 else 0
    return (x - x.mean()) / sd if sd > 1e-12 else np.zeros_like(x)


def order(score, ids, k=None):
    return np.lexsort((ids, -np.asarray(score)))[:k]


def metrics(labels, selected, k=8):
    y = np.asarray(labels)[selected[:k]]
    gains = np.array([0., 1., 3.])
    disc = 1 / np.log2(np.arange(k) + 2)
    ideal = np.sort(gains[labels])[::-1][:k] @ disc[:min(k, len(labels))]
    return {'ndcg': float(gains[y] @ disc[:len(y)] / ideal) if ideal else 0.,
            'related': float(np.sum(y >= 1) / k), 'strong': float(np.sum(y == 2) / k)}


def interval(values, groups):
    unique = sorted(set(groups))
    # Equal weight per source/intent. Resample clusters, retaining their sizes.
    sums = np.array([sum(v for v, g in zip(values, groups) if g == u) for u in unique])
    ns = np.array([groups.count(u) for u in unique])
    picks = np.random.default_rng(SEED).integers(len(unique), size=(4000, len(unique)))
    boots = sums[picks].sum(1) / ns[picks].sum(1)
    return [float(np.quantile(boots, .025)), float(np.quantile(boots, .975))]


def kernel(store, rows):
    # PSD Gram matrix; no book, volume, gene-family or category information.
    return ((store.D[rows] @ store.D[rows].T + store.R[rows] @ store.R[rows].T) / 2).astype(np.float64)


def diffuse(score, gram, alpha):
    if alpha == 0:
        return np.asarray(score).copy()
    n = len(score)
    if n < 2:
        return np.asarray(score).copy()
    dist = np.maximum(2 - 2 * gram, 0)
    np.fill_diagonal(dist, np.inf)
    # Structural hyperparameter: sqrt(n) nearest neighbours, no semantic rules.
    k = min(n - 1, max(1, int(np.sqrt(n))))
    ix = np.argsort(dist, axis=1, kind='stable')[:, :k]
    scale = np.maximum(np.take_along_axis(dist, ix[:, -1:], axis=1).ravel(), 1e-8)
    weights = np.exp(-np.take_along_axis(dist, ix, axis=1) /
                     np.sqrt(scale[:, None] * scale[ix]))
    a = sparse.csr_matrix((weights.ravel(), (np.repeat(np.arange(n), k), ix.ravel())), shape=(n, n))
    a = a.maximum(a.T)
    transition = sparse.diags(1 / np.asarray(a.sum(axis=1)).ravel()) @ a
    y = softmax(z(score))
    f = y.copy()
    for _ in range(160):
        updated = (1 - alpha) * y + alpha * (transition.T @ f)
        if np.max(np.abs(updated - f)) < 1e-10:
            f = updated
            break
        f = updated
    assert np.isfinite(f).all() and abs(f.sum() - 1) < 1e-7
    return f


def diverse(score, gram, ids, beta, k=10):
    """Greedy log-det marginal objective: sum(z(score)) + beta*log det(Gram).

    Greedy approximation, not exact DPP MAP. A small diagonal jitter handles
    duplicate/linearly dependent embeddings; beta=0 is exactly ordinary ranking.
    """
    if beta == 0:
        return order(score, ids, k)
    s = (gram + np.eye(len(score)) * 1e-6) / (1 + 1e-6)
    residual = np.diag(s).copy()
    chol = np.zeros((k, len(score)))
    selected = []
    rel = z(score)
    for j in range(min(k, len(score))):
        utility = rel + beta * np.log(np.maximum(residual, 1e-12))
        utility[selected] = -np.inf
        pick = int(order(utility, ids, 1)[0])
        selected.append(pick)
        chol[j] = (s[pick] - chol[:j, pick] @ chol[:j]) / np.sqrt(max(residual[pick], 1e-12))
        residual = np.maximum(residual - chol[j] ** 2, 0)
    return np.array(selected)


class Store:
    def __init__(self):
        import sqlite3
        ret = GEN / 'engine-pack/retrieval'
        self.ids = np.load(ret / 'verse_ids.npy')
        self.Dstored = np.load(ret / 'dense_embeddings.f16.npy').astype(np.float32)
        self.D = norm(self.Dstored)
        self.G = norm(np.load(ret / 'weighted_genome_embeddings.f16.npy').astype(np.float32))
        self.R = norm(np.load(RAW).astype(np.float32))
        self.S = sparse.load_npz(ret / 'sparse_index.csr.npz').astype(np.float32)
        lengths = np.sqrt(np.asarray(self.S.multiply(self.S).sum(1)).ravel()).clip(1e-12)
        self.Sn = sparse.diags(1 / lengths) @ self.S
        self.vol = volume_of_rows(self.ids)
        c = sqlite3.connect(f'file:{(GEN / "topics-pack-v1/topics.db").as_posix()}?mode=ro', uri=True)
        postings = list(c.execute('SELECT topic, verse_id, w FROM posting'))
        c.close()
        tid = {t: i for i, t in enumerate(sorted({t for t, _, _ in postings}))}
        self.T = sparse.csr_matrix(([w for _, _, w in postings],
                                   ([int(np.searchsorted(self.ids, v)) for _, v, _ in postings],
                                    [tid[t] for t, _, _ in postings])),
                                  shape=(len(self.ids), len(tid)), dtype=np.float32)
        self.catalog = sqlite3.connect(f'file:{(GEN / "release/catalog.db").as_posix()}?mode=ro', uri=True)
        self.content = sqlite3.connect(f'file:{(GEN / "release/content.db").as_posix()}?mode=ro', uri=True)
        self.chapters = self.catalog.execute('SELECT book_id, chapter, first_verse_id FROM chapters ORDER BY first_verse_id').fetchall()
        self.firsts = [c[2] for c in self.chapters]
        self.names = dict(self.catalog.execute('SELECT book_id, name FROM book_names_english'))

    def ref(self, v):
        b, ch, start = self.chapters[bisect.bisect_right(self.firsts, int(v)) - 1]
        return f'{self.names[b]} {ch}:{int(v) - start + 1}'

    def text(self, v):
        return self.content.execute('SELECT text FROM text_english WHERE verse_id=?', (int(v),)).fetchone()[0]

    def row(self, v):
        r = int(np.searchsorted(self.ids, v))
        assert r < len(self.ids) and self.ids[r] == v
        return r

    def similar_scores(self, src, strength):
        r = self.row(src)
        ok = np.ones(len(self.ids), dtype=bool)
        ok[r] = False
        g = (self.G @ self.G[r]).astype(np.float64)
        t = (self.T @ self.T[r].T).toarray().ravel().astype(np.float64)
        has_topic = t > 0
        g = balance(g, self.vol, ok, strength)
        t = balance(t, self.vol, ok, strength, positive_only=True)
        elig = np.flatnonzero(ok)
        tp = np.flatnonzero(ok & has_topic)
        cand = np.unique(np.r_[elig[order(g[elig], self.ids[elig], 200)],
                               tp[order(t[tp], self.ids[tp], 200)]])
        def standardize_all(x):
            sd = x[cand].std(ddof=1)
            return (x - x[cand].mean()) / sd if sd > 1e-12 else x * 0
        score = standardize_all(g) + .5 * standardize_all(t)
        score[r] = -1e9
        return score, cand

    def features(self, src, rows):
        r = self.row(src)
        scalars = np.column_stack([self.D[rows] @ self.D[r], self.R[rows] @ self.R[r],
                                   (self.Sn[rows] @ self.Sn[r].T).toarray().ravel()])
        return {'linear': scalars,
                'genome': np.column_stack([scalars, self.R[rows] * self.R[r]]),
                'topics': np.column_stack([scalars, (self.T[rows] @ self.T[r].T).toarray().ravel()])}


def fit_model(records, ix, variant, c, shuffle=False):
    scaler = StandardScaler().fit(np.concatenate([records[i]['x'][variant] for i in ix]))
    diffs, targets, weights = [], [], []
    rng = np.random.default_rng(SEED)
    for i in ix:
        rec = records[i]
        x = scaler.transform(rec['x'][variant])
        y = rng.permutation(rec['y']) if shuffle else rec['y']
        a, b = np.where(y[:, None] > y[None, :])
        if not len(a):
            continue
        d = x[a] - x[b]
        diffs.extend([d, -d])
        targets.extend([np.ones(len(a)), np.zeros(len(a))])
        weights.extend([np.full(len(a), 1 / (2 * len(a)))] * 2)
    model = LogisticRegression(C=c, fit_intercept=False, solver='lbfgs', max_iter=2000)
    model.fit(np.concatenate(diffs), np.concatenate(targets), sample_weight=np.concatenate(weights))
    assert np.max(model.n_iter_) < model.max_iter, 'ranker did not converge'
    return scaler, model


def predict(model, x):
    return model[1].decision_function(model[0].transform(x))


def splits(records, ix, n):
    groups = np.array([records[i]['group'] for i in ix])
    for tr, te in GroupKFold(n_splits=n, shuffle=True, random_state=SEED).split(ix, groups=groups):
        train, test = np.asarray(ix)[tr], np.asarray(ix)[te]
        assert not (set(groups[tr]) & set(groups[te]))
        yield train, test


def human_experiment(store):
    key = read(ROOT / 'local-benchmarks/topic-review-key.json')
    marks = read(ROOT / 'local-benchmarks/topic-judgments-from-scored-html.json')
    records = []
    for qi, entry in key.items():
        ids = np.array(sorted(int(v) for v in entry['passages'] if f'{qi}|{v}' in marks))
        rows = np.array([store.row(v) for v in ids])
        y = np.array([marks[f'{qi}|{v}'] for v in ids], dtype=int)
        assert len(ids) >= 8 and set(y) <= {0, 1, 2}
        baseline, cand = store.similar_scores(entry['source'], .75)
        old, oldcand = store.similar_scores(entry['source'], 0)
        r = store.row(entry['source'])
        records.append({'qi': qi, 'source': entry['source'], 'ids': ids, 'rows': rows, 'y': y,
                        'group': str(bisect.bisect_right(store.firsts, entry['source']) - 1),
                        'x': store.features(entry['source'], rows), 'gram': kernel(store, rows),
                        'current': baseline[rows], 'unbalanced': old[rows],
                        'full_current': store.ids[cand[order(baseline[cand], store.ids[cand], 8)]].tolist(),
                        'full_unbalanced': store.ids[oldcand[order(old[oldcand], store.ids[oldcand], 8)]].tolist(),
                        'weighted_genome': store.G[rows] @ store.G[r]})
    result = {'sources': len(records), 'judgments': sum(len(r['y']) for r in records),
              'groups': len(set(r['group'] for r in records)), 'folds': [], 'per_source': [], 'full_rankings': []}
    allix = np.arange(len(records))
    predictions = {v: {} for v in ('linear', 'genome', 'topics', 'shuffle')}
    selected_params = {}
    full_models = {}
    for fold, (tr, te) in enumerate(splits(records, allix, 5)):
        fold_info = {'fold': fold, 'train_sources': [records[i]['source'] for i in tr],
                     'test_sources': [records[i]['source'] for i in te], 'models': {}}
        for variant in ('linear', 'genome', 'topics'):
            inner_scores = {}
            inner_pred = {}
            for c in CS:
                vals, preds = [], {}
                for itr, ite in splits(records, tr, 3):
                    model = fit_model(records, itr, variant, c)
                    for i in ite:
                        r = records[i]
                        p = predict(model, r['x'][variant])
                        preds[int(i)] = p
                        vals.append(metrics(r['y'], order(p, r['ids'], 8))['ndcg'])
                inner_scores[c] = float(np.mean(vals))
                inner_pred[c] = preds
            chosen = max(CS, key=lambda c: inner_scores[c])
            model = fit_model(records, tr, variant, chosen)
            fold_info['models'][variant] = {'C': chosen, 'inner_ndcg': inner_scores,
                                             'standardized_coefficients': model[1].coef_[0].tolist()}
            for i in te:
                predictions[variant][int(i)] = predict(model, records[i]['x'][variant])
            if variant == 'linear':
                # Select structural settings on inner out-of-fold predictions only.
                def utility(a, b):
                    vals = []
                    for i in tr:
                        r = records[i]
                        p = diffuse(inner_pred[chosen][int(i)], r['gram'], a)
                        rank = diverse(p, r['gram'], r['ids'], b, 8)
                        vals.append(metrics(r['y'], rank)['ndcg'])
                    return np.mean(vals)
                alpha = max(ALPHAS, key=lambda a: utility(a, 0))
                beta = max(BETAS, key=lambda b: utility(0, b))
                fold_info['graph_alpha'] = alpha
                fold_info['diversity_beta'] = beta
                shuffled = fit_model(records, tr, variant, chosen, shuffle=True)
                for i in te:
                    selected_params[int(i)] = (alpha, beta)
                    full_models[int(i)] = model
                    predictions['shuffle'][int(i)] = predict(shuffled, records[i]['x'][variant])
        result['folds'].append(fold_info)
        print(f'human nested CV fold {fold + 1}/5 complete', flush=True)
    for i, r in enumerate(records):
        scores = {'current': r['current'], 'unbalanced': r['unbalanced'], 'weighted_genome': r['weighted_genome'],
                  'dense_only': r['x']['linear'][:, 0], 'raw_genome_only': r['x']['linear'][:, 1],
                  'sparse_only': r['x']['linear'][:, 2],
                  'equal_similarity': np.mean(np.column_stack([z(r['x']['linear'][:, j]) for j in range(3)]), axis=1),
                  **{f'learned_{v}': predictions[v][i] for v in ('linear', 'genome', 'topics')},
                  'shuffled_labels_control': predictions['shuffle'][i]}
        alpha, beta = selected_params[i]
        ranks = {name: order(p, r['ids'], 8) for name, p in scores.items()}
        ranks['learned_graph'] = order(diffuse(predictions['linear'][i], r['gram'], alpha), r['ids'], 8)
        ranks['learned_diverse'] = diverse(predictions['linear'][i], r['gram'], r['ids'], beta, 8)
        # Full grid makes it visible when model selection simply chooses no change.
        for a in ALPHAS[1:]:
            ranks[f'graph_{a}'] = order(diffuse(predictions['linear'][i], r['gram'], a), r['ids'], 8)
        for b in BETAS[1:]:
            ranks[f'diverse_{b}'] = diverse(predictions['linear'][i], r['gram'], r['ids'], b, 8)
        row = {'source': r['source'], 'group': r['group'], 'methods': {}}
        for name, selected in ranks.items():
            m = metrics(r['y'], selected)
            sub = r['gram'][np.ix_(selected, selected)]
            m['redundancy'] = float(sub[np.triu_indices(len(selected), 1)].mean())
            m['ids'] = r['ids'][selected].tolist()
            row['methods'][name] = m
        result['per_source'].append(row)
        # New discoveries: generate from full-corpus candidates without inserting known positives.
        sr = store.row(r['source'])
        raw = [store.D @ store.D[sr], store.R @ store.R[sr], (store.Sn @ store.Sn[sr].T).toarray().ravel()]
        for a in raw:
            a[sr] = -1
        cand = np.unique(np.concatenate([order(a, store.ids, 200) for a in raw]))
        x = np.column_stack([a[cand] for a in raw])
        p = predict(full_models[i], x)
        gram = kernel(store, cand)
        full = {'current': r['full_current'], 'unbalanced': r['full_unbalanced'],
                'dense_only': store.ids[order(raw[0], store.ids, 8)].tolist(),
                'learned_linear': store.ids[cand[order(p, store.ids[cand], 8)]].tolist(),
                'learned_graph': store.ids[cand[order(diffuse(p, gram, alpha), store.ids[cand], 8)]].tolist(),
                'learned_diverse': store.ids[cand[diverse(p, gram, store.ids[cand], beta, 8)]].tolist()}
        judged = dict(zip(r['ids'].tolist(), r['y'].tolist()))
        result['full_rankings'].append({'source': r['source'], 'group': r['group'], 'methods': full,
                                        'judgments': judged})
    groups = [r['group'] for r in result['per_source']]
    result['summary'] = {}
    for name in result['per_source'][0]['methods']:
        values = {m: [r['methods'][name][m] for r in result['per_source']] for m in ('ndcg', 'related', 'strong', 'redundancy')}
        delta = [r['methods'][name]['ndcg'] - r['methods']['current']['ndcg'] for r in result['per_source']]
        result['summary'][name] = {**{m: float(np.mean(v)) for m, v in values.items()},
                                   'ndcg_delta': float(np.mean(delta)), 'ndcg_delta_ci95': interval(delta, groups)}
    result['paired_diagnostics'] = {}
    for a, b in [('learned_graph', 'learned_linear'), ('learned_diverse', 'learned_linear'),
                 ('learned_linear', 'dense_only'), ('learned_linear', 'sparse_only'),
                 ('learned_linear', 'equal_similarity')]:
        delta = [r['methods'][a]['ndcg'] - r['methods'][b]['ndcg'] for r in result['per_source']]
        result['paired_diagnostics'][f'{a} minus {b}'] = {'delta': float(np.mean(delta)), 'ci95': interval(delta, groups)}
    result['full_corpus_bounds'] = {}
    for name in result['full_rankings'][0]['methods']:
        vals = [r['judgments'].get(v) for r in result['full_rankings'] for v in r['methods'][name]]
        known_positive = sum(v is not None and v >= 1 for v in vals)
        unknown = vals.count(None)
        result['full_corpus_bounds'][name] = {'judged_fraction': 1 - unknown / len(vals),
                                             'related_lower': known_positive / len(vals),
                                             'related_upper': (known_positive + unknown) / len(vals)}
    write(OUT / 'human-results.json', result)
    return result


class TokenPack:
    def __init__(self):
        p = GEN / 'colbert-pack-v1'
        self.vec, self.cum = [], []
        for path in sorted(p.glob('shard-*.vec.npy')):
            self.vec.append(np.load(path, mmap_mode='r'))
            self.cum.append(np.r_[0, np.cumsum(np.load(str(path).replace('.vec.', '.cnt.')))])

    def maxsim(self, query, rows):
        # Keep scratch bounded; no persistent copy of the multi-GB token pack.
        out = []
        for start in range(0, len(rows), 64):
            parts = []
            for r in rows[start:start + 64]:
                sh, loc = divmod(int(r), 1000)
                parts.append(self.vec[sh][self.cum[sh][loc]:self.cum[sh][loc + 1]])
            offsets = np.r_[0, np.cumsum([len(p) for p in parts])[:-1]]
            sim = query @ np.concatenate(parts).astype(np.float32).T
            out.extend(np.maximum.reduceat(sim, offsets, axis=1).mean(0))
        return np.array(out, dtype=np.float64)


def search_experiment(store):
    import onnxruntime as ort
    from tokenizers import Tokenizer
    rob = read(ROOT / 'tool/query_robustness_set.json')['intents']
    scenarios = {r['id']: r['anchors'] for r in read(ROOT / 'tool/seeker_scenarios.json')['scenarios']}
    refs = [store.ref(v) for v in store.ids]
    anchors = {}
    for it in rob:
        aa = scenarios[it['anchors_from']]
        anchors[it['id']] = {int(v) for v, ref in zip(store.ids, refs)
                             if any(ref == a or (a.endswith(':*') and ref.startswith(a[:-1])) for a in aa)}
        assert anchors[it['id']], f'unresolved anchors: {it["id"]}'
    packdir = GEN / 'engine-pack'
    manifest = read(packdir / 'manifest.json')
    so = ort.SessionOptions()
    so.intra_op_num_threads = 4
    sess = ort.InferenceSession(str(packdir / manifest['encoder_file']), so, providers=['CPUExecutionProvider'])
    tok = Tokenizer.from_file(str(packdir / 'tokenizer.json'))
    head = {k: v.astype(np.float32) for k, v in np.load(packdir / 'head.npz').items()}
    genes = (packdir / 'retrieval/gene_ids.txt').read_text().splitlines()
    fw = manifest['identity']['fusion']['family_weights']
    sw = np.sqrt(np.array([fw.get(g[0], fw['default']) for g in genes], dtype=np.float32))
    tokenpack = TokenPack()
    cache = OUT / 'search-cache'
    cache.mkdir(exist_ok=True)
    cache_identity = {'schema': 1, 'engine_manifest': digest(packdir / 'manifest.json'),
                      'raw_genome': digest(RAW), 'balance_code': digest(ROOT / 'tool/volume_balance.py'),
                      'colbert_manifest': digest(GEN / 'colbert-pack-v1/manifest.json')}
    identity_path = cache / 'identity.json'
    if identity_path.exists():
        if read(identity_path) != cache_identity:
            raise ValueError('Search cache inputs changed. Use a new experiment output directory; do not mix runs.')
    elif list(cache.glob('*.npz')):
        # Earlier v1 runs recorded the engine/raw identities in their run manifest.
        previous = read(OUT / 'manifest-search.json')['source_sha256']
        assert previous[str(Path('generated-artifacts/engine-pack/manifest.json'))] == cache_identity['engine_manifest']
        assert previous[str(RAW.relative_to(ROOT))] == cache_identity['raw_genome']
    write(identity_path, cache_identity)
    result = {'queries': [], 'proxy_only': True, 'encoder': manifest['variant'],
              'baseline_scope': 'semantic retrieval; no reference parser or entity promotion', 'grid': {}}
    t0 = time.perf_counter()
    for it in rob:
        for kind, variant in it['variants'].items():
            query = variant['text'] if isinstance(variant, dict) else variant
            path = cache / (hashlib.sha256(query.encode()).hexdigest()[:20] + '.npz')
            if path.exists():
                cached = dict(np.load(path))
            else:
                start = time.perf_counter()
                tokens = np.array([tok.encode(query).ids], dtype=np.int64)
                assert 2 < tokens.shape[1] <= 512
                dense, weights, col = sess.run(None, {'input_ids': tokens, 'attention_mask': np.ones_like(tokens)})
                dense = dense[0]
                qsp = np.zeros(store.S.shape[1], dtype=np.float32)
                for tid, w in zip(tokens[0], weights.reshape(-1)):
                    if tid > 3 and w > qsp[tid]:
                        qsp[tid] = w
                h = dense @ head['w0'].T + head['b0']
                h = .5 * h * (1 + erf(h / np.sqrt(2)))
                genome = 1 / (1 + np.exp(-(h @ head['w1'].T + head['b1'])))
                da = (store.Dstored @ dense).astype(np.float64)
                ga = (store.G @ norm(genome * sw)).astype(np.float64)
                sa = (store.S @ qsp).astype(np.float64)
                ra = (store.R @ norm(genome)).astype(np.float64)
                ok = np.ones(len(da), dtype=bool)
                db, gb = balance(da, store.vol, ok, .75), balance(ga, store.vol, ok, .75)
                cb = np.unique(np.r_[order(db, store.ids, 200), order(gb, store.ids, 200), order(sa, store.ids, 200)])
                cu = np.unique(np.r_[order(da, store.ids, 200), order(ga, store.ids, 200), order(sa, store.ids, 200)])
                cr = np.unique(np.r_[order(da, store.ids, 200), order(ra, store.ids, 200), order(sa, store.ids, 200)])
                combined = np.unique(np.r_[cb, cu, cr])
                co = tokenpack.maxsim(col[0], combined)
                colscore = np.zeros(len(store.ids))
                colscore[combined] = co
                cached = {'cb': cb, 'cu': cu, 'cr': cr,
                          'compass': .1*z(db[cb]) + .1*z(sa[cb]) + .2*z(colscore[cb]) + .6*z(gb[cb]),
                          'lantern': .25*z(db[cb]) + .15*z(sa[cb]) + .6*z(gb[cb]),
                          'unbalanced': .1*z(da[cu]) + .1*z(sa[cu]) + .2*z(colscore[cu]) + .6*z(ga[cu]),
                          'raw_features': np.column_stack([z(da[cr]), z(sa[cr]), z(colscore[cr]), z(ra[cr])]),
                          'milliseconds': np.array((time.perf_counter() - start) * 1000)}
                np.savez_compressed(path, **cached)
            cb, cu, cr = cached['cb'], cached['cu'], cached['cr']
            ids = store.ids[cr]
            features = cached['raw_features']
            equal = features.mean(1)
            gram = kernel(store, cr)
            rankings = {'compass': store.ids[cb[order(cached['compass'], store.ids[cb], 10)]],
                        'lantern': store.ids[cb[order(cached['lantern'], store.ids[cb], 10)]],
                        'compass_unbalanced': store.ids[cu[order(cached['unbalanced'], store.ids[cu], 10)]],
                        'raw_equal': ids[order(equal, ids, 10)]}
            for j, name in enumerate(('dense', 'sparse', 'colbert', 'raw_genome')):
                rankings[name] = ids[order(features[:, j], ids, 10)]
            for a in ALPHAS:
                rankings[f'graph_{a}'] = ids[order(diffuse(equal, gram, a), ids, 10)]
            for b in BETAS:
                rankings[f'diverse_{b}'] = ids[diverse(equal, gram, ids, b, 10)]
            target = anchors[it['id']]
            row = {'intent': it['id'], 'kind': kind, 'query': query,
                   'candidate_anchor_hit_current': bool(target.intersection(store.ids[cb].tolist())),
                   'candidate_anchor_hit_raw': bool(target.intersection(ids.tolist())),
                   'milliseconds': float(cached['milliseconds']), 'methods': {}}
            for name, rank in rankings.items():
                hits = [int(v) in target for v in rank]
                rr = next((1 / (i + 1) for i, h in enumerate(hits) if h), 0.)
                row['methods'][name] = {'hit5': float(any(hits[:5])), 'hit10': float(any(hits)), 'mrr10': rr,
                                        'ids': rank.tolist()}
            result['queries'].append(row)
        print(f'search {len(result["queries"])}/192 queries ({time.perf_counter() - t0:.0f}s)', flush=True)
    del sess
    # Hold every phrasing and language of an intent together; select only on training intents.
    unique = sorted(set(r['intent'] for r in result['queries']))
    folds = list(GroupKFold(n_splits=5, shuffle=True, random_state=SEED).split(unique, groups=unique))
    result['folds'] = []
    for tr, te in folds:
        train, test = {unique[i] for i in tr}, {unique[i] for i in te}
        fold = {'train_intents': sorted(train), 'test_intents': sorted(test), 'selected': {}}
        for family, choices in [('signal', ['raw_equal', 'dense', 'sparse', 'colbert', 'raw_genome']),
                                 ('graph', [f'graph_{a}' for a in ALPHAS]),
                                 ('diverse', [f'diverse_{b}' for b in BETAS])]:
            def utility(name):
                vals = [r['methods'][name] for r in result['queries'] if r['intent'] in train]
                return (np.mean([v['hit10'] for v in vals]), np.mean([v['mrr10'] for v in vals]))
            best = max(choices, key=utility)
            fold['selected'][family] = best
            for r in result['queries']:
                if r['intent'] in test:
                    r['methods'][f'selected_{family}'] = r['methods'][best]
        result['folds'].append(fold)
    groups = [r['intent'] for r in result['queries']]
    result['summary'] = {}
    for name in result['queries'][0]['methods']:
        values = {m: [r['methods'][name][m] for r in result['queries']] for m in ('hit5', 'hit10', 'mrr10')}
        delta = [r['methods'][name]['hit10'] - r['methods']['compass']['hit10'] for r in result['queries']]
        stabilities = []
        for intent in unique:
            # English paraphrases only; exclude keywords, single word, other language.
            ranks = [set(r['methods'][name]['ids']) for r in result['queries']
                     if r['intent'] == intent and r['kind'] in ('formal', 'casual', 'synonym', 'narrative', 'typo')]
            stabilities.extend([len(a & b) / len(a | b) for i, a in enumerate(ranks) for b in ranks[i+1:]])
        result['summary'][name] = {**{m: float(np.mean(v)) for m, v in values.items()},
                                   'hit10_delta': float(np.mean(delta)), 'hit10_delta_ci95': interval(delta, groups),
                                   'paraphrase_jaccard': float(np.mean(stabilities))}
    result['candidate_anchor_coverage'] = {k: float(np.mean([r[k] for r in result['queries']]))
                                           for k in ('candidate_anchor_hit_current', 'candidate_anchor_hit_raw')}
    result['by_wording'] = {kind: {name: float(np.mean([r['methods'][name]['hit10'] for r in result['queries'] if r['kind'] == kind]))
                                  for name in ('compass', 'lantern', 'raw_equal', 'selected_graph', 'selected_diverse')}
                             for kind in sorted({r['kind'] for r in result['queries']})}
    write(OUT / 'search-results.json', result)
    return result


def native_parity(human, search):
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
           'threads': 4, 'volume_balance': .75}
    err = ctypes.c_char_p()
    handle = lib.se_open(json.dumps(cfg).encode(), ctypes.byref(err))
    assert handle, err.value
    results = []
    def call(req):
        pointer = lib.se_request(handle, json.dumps(req).encode())
        try:
            response = json.loads(ctypes.string_at(pointer))
        finally:
            lib.se_free_string(pointer)
        assert 'error' not in response, response
        return [h['verse_id'] for h in response['hits']]
    try:
        if human:
            for r in human['full_rankings'][::10]:
                got = call({'op': 'similar', 'verse_id': r['source'], 'top_k': 8})
                want = r['methods']['current']
                results.append({'kind': 'similar', 'source': r['source'], 'exact': got == want, 'native': got, 'python': want})
        if search:
            for r in search['queries'][::24]:
                for profile in ('compass', 'lantern'):
                    got = call({'op': 'semantic', 'query': r['query'], 'profile': profile, 'top_k': 10})
                    want = r['methods'][profile]['ids']
                    results.append({'kind': profile, 'query': r['query'], 'exact': got == want, 'native': got, 'python': want})
    finally:
        lib.se_close(handle)
    write(OUT / 'native-parity.json', results)
    assert all(r['exact'] for r in results), 'Baseline parity failed; inspect native-parity.json before interpreting results'
    return results


def review_sheet(store, human, search):
    """Fresh blinded coverage for model discoveries; not a substitute for new intents."""
    questions = []
    if human:
        # 12 uniformly sampled source records, fixed before seeing any labels/results.
        ix = np.sort(np.random.default_rng(SEED).choice(len(human['full_rankings']), 12, replace=False))
        for i in ix:
            r = human['full_rankings'][int(i)]
            questions.append({'kind': 'similar', 'prompt': f'Passages related to {store.ref(r["source"])}',
                              'source': r['source'], 'methods': r['methods']})
    if search:
        intents = sorted({r['intent'] for r in search['queries']})
        chosen = np.random.default_rng(SEED).choice(intents, 12, replace=False)
        for intent in chosen:
            r = next(r for r in search['queries'] if r['intent'] == intent and r['kind'] == 'casual')
            questions.append({'kind': 'search', 'prompt': r['query'], 'methods': {n: r['methods'][n]['ids'][:5]
                              for n in ('compass', 'lantern', 'compass_unbalanced', 'raw_equal', 'selected_graph', 'selected_diverse')}})
    rng = np.random.default_rng(SEED)
    parts = ['<!doctype html><meta charset="utf-8"><title>Mathematical retrieval: blinded review</title>',
             '<style>body{font:17px/1.6 system-ui;max-width:900px;margin:32px auto;padding:0 20px}header{position:sticky;top:0;background:white;padding:12px;border-bottom:2px solid #aaa}article{padding:16px 0;border-bottom:1px solid #ddd}label{margin-right:20px}h2{margin-top:48px}blockquote{background:#f4f4f4;padding:16px}</style>',
             '<header><b>Blinded relevance review</b> · <span id="count"></span> <button onclick="save()">Export judgments</button></header>',
             '<p>0 = unrelated; 1 = related; 2 = directly useful / clearly the same theme. Leave uncertain items unanswered. Methods and old judgments are hidden. These are new candidate judgments on existing prompts, not an independent new-intent benchmark.</p>']
    total = 0
    for i, q in enumerate(questions):
        parts.append(f'<h2>{i+1}. {html.escape(q["prompt"])}</h2>')
        if 'source' in q:
            parts.append(f'<blockquote>{html.escape(store.text(q["source"]))}</blockquote>')
        ids = sorted({v for rank in q['methods'].values() for v in rank})
        rng.shuffle(ids)
        q['pool'] = ids
        total += len(ids)
        for v in ids:
            key = f'{i}|{v}'
            radios = ''.join(f'<label><input type="radio" name="{key}" value="{n}" onchange="mark(this)">{n}</label>' for n in range(3))
            parts.append(f'<article><b>{html.escape(store.ref(v))}</b><p>{html.escape(store.text(v))}</p>{radios}</article>')
    parts.append('''<script>
const key='scriptura-mathematical-retrieval-v1';const J=JSON.parse(localStorage.getItem(key)||'{}');
function count(){document.getElementById('count').textContent=Object.keys(J).length+' judged';}
function mark(el){J[el.name]=Number(el.value);localStorage.setItem(key,JSON.stringify(J));count();}
for(const el of document.querySelectorAll('input')){if(J[el.name]===Number(el.value))el.checked=true;}count();
function save(){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(J,null,2)],{type:'application/json'}));a.download='mathematical-retrieval-judgments.json';a.click();}
</script>''')
    (OUT / 'blinded-review.html').write_text('\n'.join(parts), 'utf-8')
    write(OUT / 'blinded-review-key.json', {'questions': questions, 'total_passages': total})
    return total


def report(human, search, parity, review_count):
    lines = ['# Mathematical retrieval: offline experiment', '',
             'This experiment changes no application code, production configuration, or data packs. See the protocol in docs/MATHEMATICAL_RETRIEVAL_EXPERIMENT.md.', '',
             '## Human-judged component experiment', '']
    if human:
        lines += [f'{human["sources"]} sources; {human["judgments"]} judgments; {human["groups"]} source-chapter groups. Five outer folds, three inner folds. Scores below rerank the same fully judged historical candidate pool. They are not full-corpus accuracy.', '',
                  '| Method | nDCG@8 | Related@8 | Strong@8 | Redundancy (lower = less similar) | Delta nDCG vs current [95%] |',
                  '|---|---:|---:|---:|---:|---|']
        for name, m in human['summary'].items():
            lo, hi = m['ndcg_delta_ci95']
            lines.append(f'| {name} | {m["ndcg"]:.4f} | {m["related"]:.4f} | {m["strong"]:.4f} | {m["redundancy"]:.4f} | {m["ndcg_delta"]:+.4f} [{lo:+.4f}, {hi:+.4f}] |')
        if 'paired_diagnostics' in human:
            lines += ['', 'Additional paired diagnostics (nDCG):', '']
            for name, m in human['paired_diagnostics'].items():
                lines.append(f'- {name}: {m["delta"]:+.4f} [{m["ci95"][0]:+.4f}, {m["ci95"][1]:+.4f}]')
        lines += ['', 'Full-corpus top-8: unjudged items remain unknown. These bounds are not confidence intervals.', '',
                  '| Method | Fraction judged | Related precision lower–upper |', '|---|---:|---:|']
        for name, m in human['full_corpus_bounds'].items():
            lines.append(f'| {name} | {m["judged_fraction"]:.1%} | {m["related_lower"]:.1%}–{m["related_upper"]:.1%} |')
    if search:
        lines += ['', '## Meaning-search proxy experiment', '',
                  '192 phrasings of 24 intents. Anchors are assistant-authored and incomplete. Anchor hit rate is not accuracy. Selected methods use five folds grouped by intent; no paraphrases cross a fold boundary. Raw variants use all genome dimensions without family weighting or volume offsets.', '',
                  '| Method | Anchor hit@5 | Anchor hit@10 | MRR@10 | Paraphrase overlap | Delta hit@10 vs Compass [95%] |',
                  '|---|---:|---:|---:|---:|---|']
        for name, m in search['summary'].items():
            lo, hi = m['hit10_delta_ci95']
            lines.append(f'| {name} | {m["hit5"]:.4f} | {m["hit10"]:.4f} | {m["mrr10"]:.4f} | {m["paraphrase_jaccard"]:.4f} | {m["hit10_delta"]:+.4f} [{lo:+.4f}, {hi:+.4f}] |')
        lines += ['', f'Candidate anchor coverage: {search["candidate_anchor_coverage"]}', '',
                  'Search timings in JSON include Python reference retrieval and three candidate pools. They are not mobile production latency.']
    lines += ['', '## Verification and limits', '',
              f'- Native baseline parity: {sum(r["exact"] for r in parity)}/{len(parity)} identical ranked lists.',
              '- Pairwise training uses unequal human grades; source chapters stay together in outer and inner folds. A shuffled-label control is included.',
              '- Fixed graph/diversity grids include a no-change setting; settings are selected without outer test labels.',
              '- Historical judgments are small, single-reviewer, topic-covered, and biased by how the original pool was retrieved. Existing representation training overlap is unknown.',
              '- Topic-assisted learning uses a curated topic index; the linear/genome candidates do not.',
              '- Reduced embedding redundancy is a geometric measure, not evidence that readers find a passage a hidden gem.',
              '- No behavioral model or multi-step trail accuracy is validated: there are no real sequential judgments available.',
              '- Bootstrap intervals are exploratory, not multiplicity-adjusted. No 95–99% certification.',
              f'- A blinded review sheet contains {review_count} pooled passages across 24 prompts. New judgments can assess discoveries; new independent intents are still needed before release.']
    lines += ['', '## Reproduce and score', '', 'From the repository root:', '',
              '```powershell', '.venv/Scripts/python.exe -I tool/mathematical_retrieval_experiment.py',
              '.venv/Scripts/python.exe -I tool/mathematical_retrieval_experiment.py --score-review PATH_TO_EXPORTED_JSON',
              '```', '', 'The second command scores only fully judged prompts, keeping missing judgments out of comparative metrics.']
    (OUT / 'report.md').write_text('\n'.join(lines) + '\n', 'utf-8')


def checks():
    ids = np.array([3, 1, 2])
    assert order(np.ones(3), ids).tolist() == [1, 2, 0]
    rng = np.random.default_rng(SEED)
    vectors = norm(rng.normal(size=(12, 20)))
    gram = vectors @ vectors.T
    scores = rng.normal(size=12)
    assert np.array_equal(diverse(scores, gram, np.arange(12), 0), order(scores, np.arange(12), 10))
    picked = diverse(scores, gram, np.arange(12), .3)
    assert len(picked) == len(set(picked)) == 10
    # First two determinant choices agree with direct determinant calculation.
    assert picked[0] == np.argmax(scores)
    utilities = [z(scores)[j] + .3*np.linalg.slogdet((gram + np.eye(12)*1e-6)[np.ix_([picked[0], j], [picked[0], j])])[1]
                 if j != picked[0] else -np.inf for j in range(12)]
    assert picked[1] == np.argmax(utilities)
    diffuse(scores, gram, .85)


def score_review(path):
    key = read(OUT / 'blinded-review-key.json')
    marks = read(path)
    assert isinstance(marks, dict) and all(type(v) is int and v in (0, 1, 2) for v in marks.values())
    per = {'similar': [], 'search': []}
    complete = 0
    for i, q in enumerate(key['questions']):
        ids = q['pool']
        if not all(f'{i}|{v}' in marks for v in ids):
            continue
        complete += 1
        y = np.array([marks[f'{i}|{v}'] for v in ids])
        positions = {v: p for p, v in enumerate(ids)}
        k = 8 if q['kind'] == 'similar' else 5
        per[q['kind']].append({name: metrics(y, [positions[v] for v in rank[:k]], k)
                               for name, rank in q['methods'].items()})
    summary = {'fully_judged_prompts': complete, 'total_prompts': len(key['questions']),
               'total_marks': len(marks), 'methods': {}}
    for kind, rows in per.items():
        if rows:
            summary['methods'][kind] = {name: {m: float(np.mean([r[name][m] for r in rows]))
                                               for m in ('ndcg', 'related', 'strong')} for name in rows[0]}
    write(OUT / 'fresh-review-results.json', summary)
    print(json.dumps(summary, indent=2))
    if not complete:
        print('No fully judged prompt yet; no comparative relevance score is claimed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=('all', 'human', 'search', 'report'), default='all')
    parser.add_argument('--score-review', type=Path, help='Score exported blinded-review judgments; only complete prompts compared')
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True, parents=True)
    checks()
    if args.score_review:
        score_review(args.score_review)
        return
    sources = [ROOT / 'docs/MATHEMATICAL_RETRIEVAL_EXPERIMENT.md', ROOT / 'tool/query_robustness_set.json',
               ROOT / 'tool/seeker_scenarios.json', ROOT / 'local-benchmarks/topic-review-key.json',
               ROOT / 'local-benchmarks/topic-judgments-from-scored-html.json', GEN / 'engine-pack/manifest.json', RAW,
               GEN / 'topics-pack-v1/topics.db', GEN / 'colbert-pack-v1/manifest.json',
               ROOT / 'engine/target/release/scripture_engine.dll', ROOT / 'tool/volume_balance.py']
    manifest = {'seed': SEED, 'python': platform.python_version(), 'numpy': np.__version__,
                'scipy': scipy.__version__, 'sklearn': sklearn.__version__,
                'source_sha256': {str(p.relative_to(ROOT)): digest(p) for p in sources},
                'script_sha256': digest(Path(__file__)), 'C_grid': CS, 'graph_grid': ALPHAS, 'diversity_grid': BETAS}
    write(OUT / 'run-manifest.json', manifest)
    write(OUT / f'manifest-{args.stage}.json', manifest)
    with threadpool_limits(limits=4):
        store = Store()
        print(f'Loaded {len(store.ids)} passages, {store.R.shape[1]} genome dimensions', flush=True)
        human = human_experiment(store) if args.stage in ('all', 'human') else None
        search = search_experiment(store) if args.stage in ('all', 'search') else None
        if human is None and (OUT / 'human-results.json').exists():
            human = read(OUT / 'human-results.json')
        if search is None and (OUT / 'search-results.json').exists():
            search = read(OUT / 'search-results.json')
        parity = native_parity(human, search)
        count = review_sheet(store, human, search)
        report(human, search, parity, count)
    print(f'Report: {OUT / "report.md"}', flush=True)


if __name__ == '__main__':
    main()
