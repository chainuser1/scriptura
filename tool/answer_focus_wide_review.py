"""Collect method-blinded pilot passages incrementally, or compile explicit reviews.

Usage: python -I tool/answer_focus_wide_review.py [--compile]
No grades are inferred from ranking scores or copied from a teacher.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import answer_focus_wide_pool as study


def collect():
    corpus = study.Corpus()
    grade = study.judgments(corpus)
    path = study.OUT / 'early-blind-sheet.json'
    items = study.read(path) if path.exists() else []
    seen = {(it['question_id'], it['verse_id']) for it in items}
    new = []
    for p in sorted((study.OUT / 'queries').glob('*.json')):
        row = study.read(p)
        if not row['complete'] or row['kind'] == 'absent':
            continue
        pooled = {v for _, _, _, ranked in study.variants(row) for v in ranked[:5]}
        for v in pooled:
            if grade(row['id'], v) is not None or (row['id'], v) in seen:
                continue
            new.append({'question_id': row['id'], 'query': row['query'], 'verse_id': v,
                        'reference': corpus.ref(v), 'context':
                        [{'reference': corpus.ref(u), 'focal': u == v, 'text': text}
                         for u, text in corpus.window(v, row['language'])]})
    new.sort(key=lambda it: hashlib.sha256(f"20261018:{it['question_id']}:{it['verse_id']}".encode()).hexdigest())
    study.write(path, items + new)
    for it in new:
        print(json.dumps(it, ensure_ascii=False))
    print('NEW', len(new))


def compile_reviews():
    study.complete_rows()  # inference must finish before final sheet is frozen
    study.review()
    sheet = study.read(study.OUT / 'blind-sheet.json')
    decisions = study.read(study.OUT / 'early-decisions.json')
    by = {(g['question_id'], g['verse_id']): g for g in decisions['items']}
    assert len(by) == len(decisions['items']), 'Duplicate explicit decisions'
    expected = {(it['question_id'], it['verse_id']) for it in sheet}
    assert set(by) == expected, 'Missing or extra decisions'
    gs = study.read(study.OUT / 'grades.json')
    gs['provenance'] = decisions['provenance']
    gs['decision_sha256'] = study.digest(study.OUT / 'early-decisions.json')
    for it in sheet:
        g = by[it['question_id'], it['verse_id']]
        assert g['grade'] in (0, 1, 2) and g['reason'].strip()
        value = {'grade': g['grade'], 'reason': g['reason']}
        old = gs['items'][it['item']]
        assert old['grade'] is None or old == value, 'Would overwrite a completed judgment'
        gs['items'][it['item']] = value
    study.write(study.OUT / 'grades.json', gs)
    print('Compiled', len(sheet), 'explicit judgments')


if __name__ == '__main__':
    compile_reviews() if '--compile' in sys.argv else collect()
