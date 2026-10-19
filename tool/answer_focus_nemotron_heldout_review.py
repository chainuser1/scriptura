"""Blind review packet + fixed-slot report for docs/ANSWER_FOCUS_NEMOTRON_HELDOUT_PROTOCOL.md, mirroring
tool/answer_focus_challengers.py's review()/report() but reading the 26 held-out questions and their
qwen/nemotron scores from local-benchmarks/answer-focus-nemotron-heldout/.

  python -I tool/answer_focus_nemotron_heldout_review.py review
  python -I tool/answer_focus_nemotron_heldout_review.py report   # after review-decisions.json is fully graded
"""
import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
import answer_focus_calibration_run as cal_run  # noqa: E402
import answer_focus_nemotron_heldout_infer as held  # noqa: E402
import answer_focus_wide_pool as wide  # noqa: E402

OUT = ROOT / 'local-benchmarks/answer-focus-nemotron-heldout'
MODELS = ('qwen', 'nemotron')


def order(scores):
    import math
    assert scores and all(x is not None and math.isfinite(x) for x in scores)
    return sorted(range(len(scores)), key=lambda i: (-scores[i], i))


def frozen(path, data):
    if path.exists():
        assert wide.read(path) == data, f'Input drift: {path}'
    else:
        wide.write(path, data)


def review():
    corpus, items, sources = wide.Corpus(), {}, []
    for r in held.rows():
        methods = [list(range(5)), order(r['reranker'][:10])[:5], order(r['reranker'])[:5]]
        for name in MODELS:
            p = OUT / name / (r['id'] + '.json')
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
    blind = sorted(items.values(), key=lambda x: hashlib.sha256(('heldout:' + x['item']).encode()).hexdigest())
    frozen(OUT / 'blind-view.json', blind)
    frozen(OUT / 'review-decisions.json', {'reviewer': '', 'review_type': '',
        'source_sha256': {str(p.relative_to(ROOT)): wide.digest(p) for p in
                          [OUT / 'blind-view.json', OUT / 'identity.json', *sources]},
        'items': [{'item': r['item'], 'grade': None, 'reason': ''} for r in blind]})
    print(f'{len(blind)} unique passages ready for blind review; no quality scores inferred.')


def report():
    """Fixed-slot P@5 (missing results count as zero) for the five frozen methods, on the 22 answerable held-out
    questions; the 4 absent-answer controls are scored separately. Requires review-decisions.json fully graded.
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
    rows = held.rows()
    out = {'scope': 'Held-out confirmation: 26 questions never used in any earlier round '
                    '(docs/ANSWER_FOCUS_NEMOTRON_HELDOUT_PROTOCOL.md).',
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
    bge = out['methods']['answer_focus_today_bge10']['direct_p5_mean']
    nem = out['methods']['nemotron_at200']['direct_p5_mean']
    gap = nem - bge
    print(f'\nNemotron vs today-shipped direct P@5 gap: {gap:+.4f} (decision rule: confirmed needs > 0.10)')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('review', 'report'))
    {'review': review, 'report': report}[parser.parse_args().action]()
