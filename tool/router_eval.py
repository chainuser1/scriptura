"""Does choosing the fusion profile by query intent beat any single fixed profile?

Uses the cached per-query signals (tool/fusion_search.py) on the labeled benchmark and the wording set, so it runs in
seconds. The router is explicit and inspectable (regex rules on the query text, English only; anything it does not
recognize falls through to the genome-heavy default), which is how it would be exposed in the app: as a visible
interpretation the user can change, never a hidden override.

  .venv\\Scripts\\python.exe -I tool/router_eval.py [--variant int8_matmul]
"""
import argparse
import json
import pickle
import re
import sqlite3
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fusion_search import Evaluator, rank_weights, zrows  # noqa: E402
from intent_eval import parse_comparison  # noqa: E402
from reference_search import DEFAULT_EXTRACTED  # noqa: E402
from validate_experiment_d import load_questions  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TEXTY = np.array([0.28, 0.14, 0.28, 0.30])      # Experiment D proportions: wording matters
GENOMIC = np.array([0.0, 0.10, 0.20, 0.70])     # robust pick from the grid search
LEAN = np.array([0.10, 0.10, 0.0, 0.80])
ENGLISH_HINT = set('the a an is are was were of to in and for with what who how why do does did i my me you your it that this about from be can have has'.split())


def looks_english(q):
    toks = re.findall(r"[a-z']+", q.lower())
    return len(toks) > 0 and sum(t in ENGLISH_HINT for t in toks) / len(toks) >= 0.2 or (len(toks) <= 3 and q.isascii())


def route(q):
    """-> (intent, weights). Order matters; first match wins."""
    ql = q.lower().strip()
    if not looks_english(q):
        return 'non-english', GENOMIC
    if parse_comparison(q):
        return 'comparison', GENOMIC
    if re.match(r'^who\s+(?:is|was|were)\b', ql):
        return 'person', TEXTY
    if re.search(r'\b(?:story of|what happened|how did|why did)\b', ql):
        return 'story', TEXTY
    if re.match(r'^(?:what\s+(?:is|are|does|do)\b|define\b|meaning of\b|what.s)', ql):
        return 'definition', TEXTY
    if len(ql.split()) <= 3 and not re.search(r'\b(i|my|me)\b', ql):
        return 'keyword', TEXTY
    if re.match(r'^(?:how\s+(?:do|can|should|to)\b|what should\b)', ql):
        return 'howto', GENOMIC
    return 'other', GENOMIC


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
    texts = {}
    for it in data:
        for k, v in it['variants'].items():
            texts[(it['id'], k)] = v['text'] if isinstance(v, dict) else v
    report = json.loads((DEFAULT_EXTRACTED / 'scripture-genome-question-hidden4096-full' / 'validation_q250.json').read_text('utf-8'))
    _q, _l, qtext, _g = load_questions(report['manifest'], 0)
    ev = Evaluator(blob['bench'], blob['word'], ref_of, anchors)

    fixed = {'Experiment D': TEXTY, 'genomic (0/.1/.2/.7)': GENOMIC, 'lean g80': LEAN}

    def routed(text):
        return lambda r: rank_weights(r, route(text)[1])

    def word_score(ranker_for, kinds=None, intents=None):
        hits = []
        for (iid, kind), r in zip(ev.wkeys, ev.wrows):
            if kinds and kind not in kinds:
                continue
            hits.append(ev.hit(ranker_for((iid, kind), r), anchors[iid]))
        return float(np.mean(hits))

    print('WORDING SET hit@10  (overall and by wording kind)')
    kinds = ['formal', 'casual', 'keyword', 'single', 'synonym', 'narrative', 'typo', 'other']
    print(f'{"profile":24s}{"ALL":>6s}' + ''.join(f'{k[:8]:>9s}' for k in kinds))
    for name, w in fixed.items():
        row = f'{name:24s}{word_score(lambda key, r, w=w: rank_weights(r, w)):6.2f}'
        for k in kinds:
            row += f'{word_score(lambda key, r, w=w: rank_weights(r, w), kinds={k}):9.2f}'
        print(row)
    rt = lambda key, r: rank_weights(r, route(texts[key])[1])  # noqa: E731
    row = f'{"ROUTED (regex)":24s}{word_score(rt):6.2f}' + ''.join(f'{word_score(rt, kinds={k}):9.2f}' for k in kinds)
    print(row)
    mix = {}
    for key in ev.wkeys:
        mix[route(texts[key])[0]] = mix.get(route(texts[key])[0], 0) + 1
    print('router decisions on the wording set:', mix)

    print('\nLABELED BENCHMARK (Recall@10 / nDCG@20, English rows routed by rule, other languages -> genomic)')
    for name, w in fixed.items():
        b = ev.bench_score(lambda r, w=w: rank_weights(r, w))
        print(f'  {name:24s} R@10 {b[0]:.4f}  nDCG {b[1]:.4f}')
    # benchmark rows: route by the actual question text and language
    by_key = {}
    for (q, l), r in zip(ev.keys, ev.rows):
        by_key[(q, l)] = r
    from validate_experiment_d import metrics
    per_q = {}
    mix = {}
    for (q, l), r in by_key.items():
        text = qtext[(q, l)]
        intent, w = route(text) if l == 'english' else ('non-english', GENOMIC)
        mix[intent] = mix.get(intent, 0) + 1
        m = metrics([int(x) for x in rank_weights(r, w)], ev.gold[q])
        per_q.setdefault(q, []).append((m['recall@10'], m['weighted_ndcg@20']))
    arr = np.array([np.mean(v, axis=0) for v in per_q.values()])
    print(f'  {"ROUTED (regex)":24s} R@10 {arr[:, 0].mean():.4f}  nDCG {arr[:, 1].mean():.4f}')
    print('router decisions on the benchmark (english rows):', {k: v for k, v in mix.items()})
    return 0


if __name__ == '__main__':
    sys.exit(main())
