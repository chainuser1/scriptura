"""Orchestrates docs/ANSWER_FOCUS_KEYWORD_CONCENTRATION_PROTOCOL.md after answer_focus_concentration_infer.py has run
all three splits. Extends the 5-input monotonic logistic (dense, sparse, colbert, genome, bge_logit) to 6 inputs by
adding keyword concentration, left unconstrained (no sign assumption). Same CV diagnostic, calibration and final-test
discipline as the richer-inputs stage. Never imported by the app.

  python -I tool/answer_focus_concentration_run.py fit        # CV + fitted model -> model.json
  python -I tool/answer_focus_concentration_run.py calibrate  # Platt + cutoff -> calibration.json
  python -I tool/answer_focus_concentration_run.py test-new-items  # lists passages needing a blind grade
  python -I tool/answer_focus_concentration_run.py test-report     # method 7 vs. the frozen 5-feature baseline
"""
import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
import answer_focus_calibration_fit as fit2  # noqa: E402  (grouped_folds, Platt, choose_cutoff, log_loss)
import answer_focus_calibration_run as cal_run  # noqa: E402
import answer_focus_concentration_fit as fitc  # noqa: E402
import answer_focus_concentration_infer as conc  # noqa: E402
import answer_focus_richer_inputs_fit as fitn  # noqa: E402  (MatrixScaler: feature-count agnostic)
import answer_focus_richer_inputs_run as rich_run  # noqa: E402  (the 5-feature baseline this compares against)
import answer_focus_wide_pool as wide  # noqa: E402

OUT = ROOT / 'local-benchmarks/answer-focus-concentration'
L2 = 1.0
FEATURE_NAMES = ['dense', 'sparse', 'colbert', 'genome', 'bge_logit', 'concentration']
MONOTONIC = [True, True, True, True, True, False]  # protocol: concentration's sign is not assumed


def manifest(paths):
    return {str(p.relative_to(ROOT)): wide.digest(p) for p in paths}


def verify(hashes):
    assert hashes, 'Missing provenance hashes'
    for name, expected in hashes.items():
        assert wide.digest(ROOT / name) == expected, f'Stale artifact: {name}'


def save_new(name, data):
    path = OUT / name
    if path.exists():
        assert wide.read(path) == data, f'Refusing to overwrite {path}; use a new experiment directory'
    else:
        wide.write(path, data)


def build_feature_matrix_6(rows):
    """rows: from answer_focus_concentration_infer.rows(split). Returns (X, y, question_ids, kept_indices_per_row)
    for only the candidates with an existing grade; X columns are FEATURE_NAMES.
    """
    X, y, qid, idx = [], [], [], []
    for r in rows:
        kept = [i for i, g in enumerate(r['grades']) if g is not None]
        for i in kept:
            X.append([*r['lanes'][i], r['reranker'][i], r['concentration'][i]])
            y.append(1.0 if r['grades'][i] == 2 else 0.0)
            qid.append(r['id'])
        idx.append(kept)
    return np.array(X).reshape(-1, 6), np.array(y), np.array(qid), idx


def cross_validate_6(X, y, qid, seed=0, k=5):
    folds = fit2.grouped_folds(qid, k=k, seed=seed)
    losses = []
    for val_idx in folds:
        train_idx = np.setdiff1d(np.arange(len(y)), val_idx)
        scaler = fitn.MatrixScaler.fit(X[train_idx])
        Xz_train, Xz_val = scaler.apply(X[train_idx]), scaler.apply(X[val_idx])
        w_train = cal_run.question_weights(qid[train_idx])
        w_val = cal_run.question_weights(qid[val_idx])
        model = fitc.fit_partially_monotonic(Xz_train, y[train_idx], l2=L2, weight=w_train, monotonic=MONOTONIC)
        p = model.predict_proba(Xz_val)
        losses.append(fit2.log_loss(y[val_idx], p, weight=w_val))
    return losses


def run_fit():
    verify(wide.read(conc.OUT / 'identity.json')['sha256'])
    train_rows = conc.rows('train')
    X, y, qid, _ = build_feature_matrix_6(train_rows)
    losses = cross_validate_6(X, y, qid)
    mean_loss = float(np.mean(losses))

    scaler = fitn.MatrixScaler.fit(X)
    Xz = scaler.apply(X)
    w_all = cal_run.question_weights(qid)
    model = fitc.fit_partially_monotonic(Xz, y, l2=L2, weight=w_all, monotonic=MONOTONIC)

    out = {
        'scope': 'Grouped 5-fold CV on train (72 questions), 6-feature model (concentration unconstrained). '
                 'Frozen 5-feature baseline for comparison: CV log loss 0.6268 '
                 '(docs/ANSWER_FOCUS_RICHER_INPUTS_RESULTS.md), 2-feature baseline 0.628.',
        'rows': len(y), 'questions': len(np.unique(qid)), 'l2': L2, 'monotonic': MONOTONIC,
        'cv_log_loss_mean': round(mean_loss, 4), 'cv_log_loss_per_fold': losses,
        'baseline_5feature_cv_log_loss': 0.6268,
        'cv_improvement_vs_5feature': round(0.6268 - mean_loss, 4),
        'scaler': {'mean': scaler.mean.tolist(), 'std': scaler.std.tolist()},
        'model': {'weights': model.weights.tolist(), 'intercept': model.intercept},
        'feature_weights_named': dict(zip(FEATURE_NAMES, model.weights.tolist())),
        'source_sha256': manifest([Path(__file__), Path(fitc.__file__), Path(conc.__file__),
                                  ROOT / 'docs/ANSWER_FOCUS_KEYWORD_CONCENTRATION_PROTOCOL.md',
                                  *sorted((conc.OUT / 'queries/train').glob('*.json'))]),
    }
    save_new('model.json', out)
    print(f'6-feature CV log loss: {mean_loss:.4f} {losses}')
    print(f'vs 5-feature baseline 0.6268: {"+" if 0.6268 - mean_loss >= 0 else ""}{0.6268 - mean_loss:.4f}')
    print('weights:', out['feature_weights_named'])
    print(f'  concentration weight sign: {"positive" if model.weights[5] >= 0 else "negative"} '
          f'(unconstrained -- this is itself a finding, not assumed)')


def run_calibrate():
    model_info = wide.read(OUT / 'model.json')
    verify(model_info['source_sha256'])
    scaler = fitn.MatrixScaler(mean=np.array(model_info['scaler']['mean']), std=np.array(model_info['scaler']['std']))
    weights = np.array(model_info['model']['weights'])
    intercept = model_info['model']['intercept']
    calibration_rows = conc.rows('calibration')
    lanes_by_q = {r['id']: r for r in calibration_rows}

    grades_path = cal_run.OUT / 'grades.json'
    assert grades_path.exists(), f'expected the frozen calibration grades at {grades_path}'
    compiled = wide.read(grades_path)
    sheet = wide.read(cal_run.OUT / 'review-sheet.json')
    old_grades = {(row['question_id'], row['verse_id']): compiled['items'][row['item']]['grade'] for row in sheet}

    rows_by_q = {}
    for row in sheet:
        rows_by_q.setdefault(row['question_id'], []).append(row)
    logits, labels, weight_list = [], [], []
    for qid_, rows in rows_by_q.items():
        q_weight = 1.0 / sum(1.0 / r['inclusion_probability'] for r in rows)
        lr = lanes_by_q[qid_]
        cand_pos = {v: i for i, v in enumerate(lr['candidates'])}
        for row in rows:
            v = row['verse_id']
            if v not in cand_pos:
                continue
            i = cand_pos[v]
            x = scaler.apply(np.array([[*lr['lanes'][i], lr['reranker'][i], lr['concentration'][i]]]))
            z = float(weights @ x[0] + intercept)
            logits.append(z)
            labels.append(1.0 if old_grades[(qid_, v)] == 2 else 0.0)
            weight_list.append(q_weight / row['inclusion_probability'])
    logits, labels, weight_arr = np.array(logits), np.array(labels), np.array(weight_list)
    platt = fit2.fit_platt(logits, labels, weight_arr)
    probs = platt.apply(logits)
    cutoff, f1 = fit2.choose_cutoff(probs, labels, weight_arr)
    out = {'scope': '6-feature Platt + cutoff, same 120-row calibration sample and grades as the frozen baseline '
                    '(no new review). Baseline 5-feature F1 at cutoff: 0.2857.',
           'rows': len(labels), 'platt': {'slope': platt.slope, 'intercept': platt.intercept},
           'cutoff': cutoff, 'f1_at_cutoff': f1, 'baseline_5feature_f1': 0.2857,
           'f1_improvement_vs_5feature': round(f1 - 0.2857, 4),
           'source_sha256': manifest([OUT / 'model.json', Path(__file__)])}
    save_new('calibration.json', out)
    print(f'Platt slope={platt.slope:.4f} intercept={platt.intercept:.4f}; cutoff={cutoff:.2f} (F1={f1:.4f}) '
          f'on {len(labels)} rows; vs 5-feature baseline 0.2857: '
          f'{"+" if f1 - 0.2857 >= 0 else ""}{f1 - 0.2857:.4f}')


def _scores(model_info, r):
    scaler = fitn.MatrixScaler(mean=np.array(model_info['scaler']['mean']), std=np.array(model_info['scaler']['std']))
    weights = np.array(model_info['model']['weights'])
    X = scaler.apply(np.array([[*lanes, bge, c] for lanes, bge, c in zip(r['lanes'], r['reranker'], r['concentration'])]))
    z = X @ weights + model_info['model']['intercept']
    return z, np.argsort(-z)


def method7_top5(model_info, test_rows):
    out = {}
    for r in test_rows:
        _, order = _scores(model_info, r)
        out[r['id']] = [r['candidates'][i] for i in order[:5]]
    return out


def method7b_top5_cutoff(model_info, calibration, test_rows):
    platt = fit2.Platt(**calibration['platt'])
    cutoff = calibration['cutoff']
    out = {}
    for r in test_rows:
        z, order = _scores(model_info, r)
        probs = platt.apply(z)
        out[r['id']] = [r['candidates'][i] for i in order if probs[i] >= cutoff][:5]
    return out


def run_test_new_items():
    model_info = wide.read(OUT / 'model.json')
    verify(model_info['source_sha256'])
    test_rows = conc.rows('test')
    top5 = method7_top5(model_info, test_rows)
    grades = wide.read(cal_run.OUT / 'test-topfive-grades.json')['items']
    graded_keys = {(item.rsplit(':', 1)[0], int(item.rsplit(':', 1)[1])) for item in grades}
    rich_grades_path = rich_run.OUT / 'method6-new-grades.json'
    if rich_grades_path.exists():
        for it in wide.read(rich_grades_path)['items']:
            qid_, v = it['item'].rsplit(':', 1)
            graded_keys.add((qid_, int(v)))
    new_items = sorted({(qid_, v) for qid_, vs in top5.items() for v in vs if (qid_, v) not in graded_keys})
    save_new('method7-new-items.json', {'items': [f'{q}:{v}' for q, v in new_items]})
    print(f'{len(new_items)} new passages in method 7 top-5 need a blind review:')
    for q, v in new_items:
        print(f'  {q}:{v}')


def run_test_report():
    model_info = wide.read(OUT / 'model.json')
    calibration = wide.read(OUT / 'calibration.json')
    verify(model_info['source_sha256'])
    verify(calibration['source_sha256'])
    test_rows = conc.rows('test')
    methods = {'concentration_unfiltered': method7_top5(model_info, test_rows),
              'concentration_plus_cutoff': method7b_top5_cutoff(model_info, calibration, test_rows)}

    by_key = {}
    for item, g in wide.read(cal_run.OUT / 'test-topfive-grades.json')['items'].items():
        qid_, v = item.rsplit(':', 1)
        by_key[(qid_, int(v))] = g['grade']
    rich_grades_path = rich_run.OUT / 'method6-new-grades.json'
    if rich_grades_path.exists():
        for it in wide.read(rich_grades_path)['items']:
            qid_, v = it['item'].rsplit(':', 1)
            by_key[(qid_, int(v))] = it['grade']
    new_grades_path = OUT / 'method7-new-grades.json'
    if new_grades_path.exists():
        for it in wide.read(new_grades_path)['items']:
            qid_, v = it['item'].rsplit(':', 1)
            assert it['grade'] in (0, 1, 2) and it['reason'].strip(), f'ungraded: {it["item"]}'
            by_key[(qid_, int(v))] = it['grade']
    for qid_, displayed in methods['concentration_plus_cutoff'].items():
        for v in displayed:
            assert (qid_, v) in by_key, f'unexpected new passage from the filtered method: {qid_}:{v}'

    def grade_fn(qid_, v):
        return by_key.get((qid_, v))

    cal_rows = {r['id']: r for r in cal_run.cal.rows('test')}
    out = {'scope': '6-feature (concentration-augmented) model vs. the frozen 5-feature baseline and today\'s '
                    'shipped Answer Focus, same test split and fixed-slot scoring.', 'methods': {}}
    for name, top5 in methods.items():
        per_question, absent_counts = [], {}
        for qid_, displayed in top5.items():
            scored = cal_run.score_method(qid_, displayed, grade_fn)
            scored['question_id'] = qid_
            if cal_rows[qid_]['kind'] == 'absent':
                absent_counts[qid_] = scored['displayed']
            else:
                per_question.append(scored)
        out['methods'][name] = {
            'direct_p5_mean': round(sum(r['direct_p5'] for r in per_question) / len(per_question), 4),
            'related_p5_mean': round(sum(r['related_p5'] for r in per_question) / len(per_question), 4),
            'any_direct_rate': round(sum(r['any_direct'] for r in per_question) / len(per_question), 4),
            'mean_displayed': round(sum(r['displayed'] for r in per_question) / len(per_question), 2),
            'per_question': per_question, 'absent_question_result_counts': absent_counts,
        }
    save_new('test-report.json', out)
    for name, s in out['methods'].items():
        print(f"{name:26s} direct_p5={s['direct_p5_mean']:.3f} related_p5={s['related_p5_mean']:.3f} "
              f"any_direct={s['any_direct_rate']:.3f} mean_shown={s['mean_displayed']:.1f} "
              f"absent_counts={s['absent_question_result_counts']}")
    print('\nFrozen baselines, for comparison:')
    print('  answer_focus_today_k10 (2-input)   direct_p5=0.350 related_p5=0.550 any_direct=0.625')
    print('  learned_plus_cutoff (2-input)      direct_p5=0.350 related_p5=0.550 any_direct=0.750')
    print('  richer_unfiltered (5-input)        direct_p5=0.375 related_p5=0.600 any_direct=0.625')
    print('  richer_plus_cutoff (5-input)       direct_p5=0.375 related_p5=0.550 any_direct=0.625')
    print('\nDecision rule (frozen): a real win needs CV log loss improvement > 0.01 AND final-test direct P@5 '
          'improvement > 0.125 (more than one question on 8), with no regression on any-direct or abstention.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('action', choices=('fit', 'calibrate', 'test-new-items', 'test-report'))
    {'fit': run_fit, 'calibrate': run_calibrate, 'test-new-items': run_test_new_items,
     'test-report': run_test_report}[p.parse_args().action]()
