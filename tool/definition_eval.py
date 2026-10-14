"""Does boosting verses stored as definitional passages (genome A24 form_definition_explanation) help "what is X?" queries
without hurting anything else?  Offline, on the cached signals.

  .venv\\Scripts\\python.exe -I tool/definition_eval.py [--variant int8_matmul]
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
from reference_search import DEFAULT_EXTRACTED, zscore  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFINITIONAL = {'atonement', 'faith', 'repentance', 'grace', 'baptism', 'holyghost', 'born-again', 'humility', 'tithing', 'sabbath', 'purpose'}
GENOMIC = np.array([0.0, 0.10, 0.20, 0.70])
TEXTY = np.array([0.28, 0.14, 0.28, 0.30])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--variant', default='int8_matmul')
    a = ap.parse_args()
    blob = pickle.load(open(ROOT / '.artifact-staging' / 'validation' / f'signals-{a.variant}.pkl', 'rb'))
    bundle = DEFAULT_EXTRACTED / 'scripture-retrieval-english-v1'
    genes = [l.strip() for l in (bundle / 'gene_ids.txt').read_text('utf-8').split('\n') if l.strip()]
    raw = np.load(bundle / 'genome_vectors.f16.npy', allow_pickle=False).astype(np.float32)
    vids = np.load(bundle / 'verse_ids.npy', allow_pickle=False)
    row_of = {int(v): i for i, v in enumerate(vids)}
    flag = raw[:, genes.index('A24_form_definition_explanation')]
    c = sqlite3.connect(f'file:{(DEFAULT_EXTRACTED.parent / "databases" / "scriptures_genome.db").as_posix()}?mode=ro', uri=True)
    ref_of = dict(c.execute('SELECT verse_id, reference FROM scriptures_english'))
    scen = {x['id']: x['anchors'] for x in json.loads((ROOT / 'tool' / 'seeker_scenarios.json').read_text('utf-8'))['scenarios']}
    intents = json.loads((ROOT / 'tool' / 'query_robustness_set.json').read_text('utf-8'))['intents']
    anchors = {it['id']: scen[it['anchors_from']] for it in intents}
    ev = Evaluator(blob['bench'], blob['word'], ref_of, anchors)
    flag_of = lambda r: flag[[row_of[int(i)] for i in r['ids']]]  # noqa: E731

    def with_flag(base, lam):
        def f(r):
            sc = base @ r['Z'] + lam * zscore(flag_of(r))
            return r['ids'][np.lexsort((r['ids'], -sc))[:20]]
        return f

    def word(ranker, kinds=None, only=None):
        hits, mrr = [], []
        for (iid, kind), r in zip(ev.wkeys, ev.wrows):
            if kinds and kind not in kinds or only and iid not in only:
                continue
            top = [ref_of[int(v)] for v in ranker(r)[:10]]
            an = anchors[iid]
            pos = next((i for i, t in enumerate(top) if any(t == x or (x.endswith(':*') and t.startswith(x[:-1])) for x in an)), None)
            hits.append(float(pos is not None))
            mrr.append(0.0 if pos is None else 1.0 / (pos + 1))
        return np.mean(hits), np.mean(mrr)

    print('definitional intents (11), wordings formal/casual/keyword/single  |  all other intents, all wordings  |  labeled benchmark')
    print(f'{"profile":34s}{"def hit@10":>11s}{"def MRR":>9s}{"other hit":>11s}{"bench R@10":>12s}{"nDCG@20":>9s}')
    kinds = {'formal', 'casual', 'keyword', 'single'}
    others = {it['id'] for it in intents} - DEFINITIONAL
    rows = [('Experiment D', lambda r: rank_weights(r, TEXTY)), ('genomic (0/.1/.2/.7)', lambda r: rank_weights(r, GENOMIC))]
    for lam in (0.15, 0.3, 0.6, 1.0):
        rows.append((f'genomic + {lam:.2f} x A24', with_flag(GENOMIC, lam)))
    for lam in (0.3, 0.6):
        rows.append((f'Experiment D + {lam:.2f} x A24', with_flag(TEXTY, lam)))
    for name, fn in rows:
        h, m = word(fn, kinds=kinds, only=DEFINITIONAL)
        ho, _ = word(fn, only=others)
        b = ev.bench_score(fn)
        print(f'{name:34s}{h:11.2f}{m:9.2f}{ho:11.2f}{b[0]:12.4f}{b[1]:9.4f}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
