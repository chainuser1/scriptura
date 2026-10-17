"""Unsupervised geometry diagnostics for existing retrieval representations.

No relevance judgments, model fitting, pack edits, or application changes.
Run with the project Python environment. Outputs are private local benchmarks.
"""
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parent.parent
RET = ROOT / 'generated-artifacts/engine-pack/retrieval'
RAW = ROOT / '.artifact-staging/import-application-v1/extracted/scripture-retrieval-english-v1/genome_vectors.f16.npy'
OUT = ROOT / 'local-benchmarks/retrieval-research-v2'
SEED = 20261017


def normalized(x):
    return x / np.linalg.norm(x, axis=1, keepdims=True).clip(1e-12)


def occupancy(counts):
    n = len(counts)
    return {'max_occurrences': int(counts.max()),
            'unique_passages': int(np.count_nonzero(counts)),
            'top_one_percent_passage_share': float(np.sort(counts)[-int(np.ceil(n * .01)):].sum() / counts.sum())}


def diagnose(path):
    start = time.perf_counter()
    matrix = normalized(np.load(path).astype(np.float32))
    n, dim = matrix.shape
    rng = np.random.default_rng(SEED)
    sample = matrix[rng.choice(n, min(n, 8192), replace=False)].astype(np.float64)
    mean = sample.mean(0)
    centered = sample - mean
    eigen = np.linalg.eigvalsh(centered.T @ centered / (len(sample) - 1)).clip(0)[::-1]
    probabilities = eigen / eigen.sum()
    positive = probabilities[probabilities > 0]
    random_cos = np.sum(sample[:4096] * sample[4096:8192], axis=1)
    queries = rng.choice(n, 2048, replace=False)
    counts = np.zeros(n, dtype=np.int64)
    for offset in range(0, len(queries), 64):
        rows = queries[offset:offset + 64]
        similarities = matrix[rows] @ matrix.T
        similarities[np.arange(len(rows)), rows] = -np.inf
        # Ordering within the ten is not used; approximate ties do not affect the diagnostic conclusion.
        neighbors = np.argpartition(similarities, -10, axis=1)[:, -10:]
        assert not np.any(neighbors == rows[:, None])
        counts += np.bincount(neighbors.ravel(), minlength=n)
    # Finite-sample reference: uniformly choose ten unique non-self passages per source.
    controls = []
    for _ in range(100):
        draws = []
        for q in queries:
            pick = rng.choice(n - 1, 10, replace=False)
            draws.extend(pick + (pick >= q))
        controls.append(occupancy(np.bincount(draws, minlength=n)))
    result = {'rows': n, 'dimensions': dim, 'sample_size': len(sample),
              'mean_direction_norm': float(np.linalg.norm(mean)),
              'random_pair_cosine_mean': float(random_cos.mean()),
              'random_pair_cosine_p05_p95': np.quantile(random_cos, [.05, .95]).tolist(),
              'centered_spectrum_top1_fraction': float(probabilities[0]),
              'centered_spectrum_top10_fraction': float(probabilities[:10].sum()),
              'centered_effective_rank_entropy': float(np.exp(-np.sum(positive * np.log(positive)))),
              'dimensions_for_90_percent_centered_variance': int(np.searchsorted(np.cumsum(probabilities), .90) + 1),
              'neighbor_queries': len(queries), 'neighbors_per_query': 10, 'neighbor_occupancy': occupancy(counts),
              'uniform_occupancy_reference': {key: {'mean': float(np.mean([c[key] for c in controls])),
                                                   'p025_p975': np.quantile([c[key] for c in controls], [.025, .975]).tolist()}
                                              for key in controls[0]},
              'seconds': time.perf_counter() - start}
    print(path.name, json.dumps(result['neighbor_occupancy']), flush=True)
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    paths = {'dense': RET / 'dense_embeddings.f16.npy',
             'weighted_genome': RET / 'weighted_genome_embeddings.f16.npy', 'raw_genome': RAW}
    result = {'seed': SEED, 'purpose': 'Unsupervised corpus geometry only; not retrieval relevance or accuracy.'}
    with threadpool_limits(limits=4):
        result['representations'] = {name: diagnose(path) for name, path in paths.items()}
    cached = ROOT / 'local-benchmarks/mathematical-retrieval-v1/search-cache'
    correlations = []
    for path in sorted(cached.glob('*.npz')):
        with np.load(path) as data:
            features = data['raw_features'].astype(np.float64)
        if np.all(features.std(0) > 1e-10):
            correlations.append(np.corrcoef(features.T))
    result['score_correlation'] = {'queries': len(correlations), 'signals': ['dense', 'sparse', 'colbert', 'raw_genome'],
                                   'mean_within_query_pearson': np.mean(correlations, axis=0).tolist() if correlations else None,
                                   'note': 'Correlation among scores in previously retrieved candidate pools, not relevance errors or independent evidence.'}
    result['files'] = {}
    for name, path in paths.items():
        with path.open('rb') as f:
            result['files'][name] = {'path': str(path.relative_to(ROOT)), 'sha256': hashlib.file_digest(f, 'sha256').hexdigest()}
    (OUT / 'geometry-diagnostics.json').write_text(json.dumps(result, indent=2, allow_nan=False), 'utf-8')
    print('Wrote', OUT / 'geometry-diagnostics.json', flush=True)


if __name__ == '__main__':
    main()
