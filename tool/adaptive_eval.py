"""Can the retrieval signals themselves tell when to trust wording and when to trust the genome?

A query about a named person or a specific story produces a few verses that stand far above everything else on the
text signals (dense / ColBERT): a sharp peak. An abstract or personal question produces a diffuse text profile. This
measures that peakedness, checks whether it predicts which profile (text-heavy vs genome-heavy) is better per query,
and evaluates a continuous blend between the two profiles driven by it. No intent keywords involved.

  .venv\\Scripts\\python.exe -I tool/adaptive_eval.py [--variant int8_matmul]
"""
import argparse
import json
import pickle
import sqlite3
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fusion_search import Evaluator, rank_weights  # noqa: E402
from reference_search import DEFAULT_EXTRACTED  # noqa: E402
from validate_experiment_d import metrics  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TEXTY = np.array([0.28, 0.14, 0.28, 0.30])
GENOMIC = np.array([0.0, 0.10, 0.20, 0.70])


def peak(r, rows=(0, 2)):
    """How far the best candidate stands above the rest on the text signals (max z of dense+ColBERT mean)."""
    z = r['Z'][list(rows)].mean(axis=0)
    return float(np.max(z))


def gap(r, rows=(0, 2)):
    z = np.sort(r['Z'][list(rows)].mean(axis=0))[::-1]
    return float(z[0] - z[min(4, len(z) - 1)])


def agreement(r, k=10):
    a = set(rank_weights(r, TEXTY, k).tolist())
    b = set(rank_weights(r, GENOMIC, k).tolist())
    return len(a & b) / k


def auc(x, y):
    """P(feature higher for positives than negatives), ties half."""
    x, y = np.asarray(x), np.asarray(y)
    pos, neg = x[y == 1], x[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float('nan')
    return float(np.mean([(p > n) + 0.5 * (p == n) for p in pos for n in neg]))


def adaptive_weights(r, lo, hi, feature=peak):
    t = np.clip((feature(r) - lo) / max(hi - lo, 1e-9), 0.0, 1.0)
    return t * TEXTY + (1 - t) * GENOMIC


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--variant', default='int8_matmul')
    a = ap.parse_args()
    blob = pickle.load(open(ROOT / '.artifact-staging' / 'validation' / f'signals-{a.variant}.pkl', 'rb'))
    c = sqlite3.connect(f'file:{(DEFAULT_EXTRACTED.parent / "databases" / "scriptures_genome.db").as_posix()}?mode=ro', uri=True)
    ref_of = dict(c.execute('SELECT verse_id, reference FROM scriptures_english'))
    scen = {x['id']: x['anchors'] for x in json.loads((ROOT / 'tool' / 'seeker_scenarios.json').read_text('utf-8'))['scenarios']}
    data = json.loads((ROOT / 'tool' / 'query_robustness_set.json').read_text('utf-8'))['intents']
    anchors = {it['id']: scen[it['anchors_from']] for it in data}
    ev = Evaluator(blob['bench'], blob['word'], ref_of, anchors)

    # per-row gain of TEXTY over GENOMIC, and the features
    feats, gains, src = [], [], []
    for key, r in zip(ev.keys, ev.rows):
        mt = metrics([int(x) for x in rank_weights(r, TEXTY)], ev.gold[key[0]])['recall@10']
        mg = metrics([int(x) for x in rank_weights(r, GENOMIC)], ev.gold[key[0]])['recall@10']
        feats.append((peak(r), gap(r), agreement(r), peak(r, (2,)), peak(r, (0,))))
        gains.append(mt - mg)
        src.append('bench')
    for (iid, kind), r in zip(ev.wkeys, ev.wrows):
        ht = ev.hit(rank_weights(r, TEXTY), anchors[iid])
        hg = ev.hit(rank_weights(r, GENOMIC), anchors[iid])
        feats.append((peak(r), gap(r), agreement(r), peak(r, (2,)), peak(r, (0,))))
        gains.append(ht - hg)
        src.append('word')
    F, G, S = np.array(feats), np.array(gains), np.array(src)
    names = ['peak(dense+colbert)', 'gap top1-top5', 'agreement@10', 'peak(colbert)', 'peak(dense)']
    print('does the feature predict "text-heavy beats genome-heavy" for that query? (AUC 0.5 = no signal)')
    print(f'{"feature":24s}{"AUC benchmark":>15s}{"AUC wording":>13s}{"median on bench":>17s}')
    for j, n in enumerate(names):
        row = f'{n:24s}'
        for s in ('bench', 'word'):
            m = S == s
            win, lose = G[m] > 0, G[m] < 0
            sel = win | lose
            row += f'{auc(F[m][sel][:, j], win[sel].astype(int)):>15.3f}' if s == 'bench' else f'{auc(F[m][sel][:, j], win[sel].astype(int)):>13.3f}'
        row += f'{np.median(F[S == "bench"][:, j]):>17.2f}'
        print(row)
    print(f'share of queries where text-heavy strictly wins / loses: bench {np.mean(G[S=="bench"] > 0):.2f} / {np.mean(G[S=="bench"] < 0):.2f}; '
          f'wording {np.mean(G[S=="word"] > 0):.2f} / {np.mean(G[S=="word"] < 0):.2f}')

    # adaptive blend: lambda from peak, thresholds from percentiles of the benchmark+wording pool (two-fold cross-fit)
    pool = F[:, 0]
    print('\nadaptive blend  lambda = clip((peak - lo)/(hi - lo))   (cross-fit: thresholds chosen on the other half)')
    print(f'{"percentiles (lo,hi)":22s}{"bench R@10":>12s}{"nDCG@20":>9s}{"wording hit":>13s}')
    ref = {'Experiment D (fixed)': lambda r: rank_weights(r, TEXTY), 'genomic (fixed)': lambda r: rank_weights(r, GENOMIC)}
    for n, fn in ref.items():
        b = ev.bench_score(fn)
        print(f'{n:22s}{b[0]:12.4f}{b[1]:9.4f}{ev.word_score(fn):13.3f}')
    for plo, phi in ((50, 90), (60, 95), (75, 97), (80, 99), (90, 99)):
        lo, hi = np.percentile(pool, [plo, phi])
        fn = lambda r, lo=lo, hi=hi: rank_weights(r, adaptive_weights(r, lo, hi))  # noqa: E731
        b = ev.bench_score(fn)
        print(f'{f"p{plo}-p{phi} ({lo:.1f},{hi:.1f})":22s}{b[0]:12.4f}{b[1]:9.4f}{ev.word_score(fn):13.3f}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
