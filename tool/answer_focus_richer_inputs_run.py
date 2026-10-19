"""Orchestrates docs/ANSWER_FOCUS_RICHER_INPUTS_PROTOCOL.md after answer_focus_richer_inputs_infer.py has run all
three splits. Compares a 5-input monotonic logistic model against HistGradientBoostingClassifier by grouped CV log
loss on train, picks the winner (ties within 0.01 prefer the logistic model, per protocol), calibrates it on the
existing 120-row calibration sample, and reports it as method 6 against the frozen baseline's test-report numbers.
Never imported by the app.

  python -I tool/answer_focus_richer_inputs_run.py fit        # CV comparison + both fitted models -> models.json
  python -I tool/answer_focus_richer_inputs_run.py calibrate  # Platt + cutoff for the chosen model -> calibration.json
  python -I tool/answer_focus_richer_inputs_run.py test-report  # method 6 vs. the frozen baseline -> test-report.json
"""
import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
import answer_focus_calibration_fit as fit2  # noqa: E402  (grouped_folds, Platt, choose_cutoff: feature-count agnostic)
import answer_focus_calibration_run as cal_run  # noqa: E402  (frozen 2-feature orchestration: the comparison point)
import answer_focus_richer_inputs_fit as fitn  # noqa: E402
import answer_focus_richer_inputs_infer as rich  # noqa: E402
import answer_focus_wide_pool as wide  # noqa: E402

OUT = rich.OUT
L2 = 1.0  # same as the frozen 2-feature model (docs/ANSWER_FOCUS_CALIBRATION_PROTOCOL.md)
TIE_BAND = 0.01  # protocol: "If models 2 and 3 tie within 0.01 log loss, prefer model 2"


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


def build_feature_matrix(rows):
    """rows: from answer_focus_richer_inputs_infer.rows(split). Returns (X, y, question_ids, kept_indices_per_row)
    for only the candidates with an existing grade; X columns are [dense, sparse, colbert, genome, bge_logit].
    kept_indices_per_row[j] is the list of candidate-list positions used from rows[j], for traceability back to verse IDs.
    """
    X, y, qid, idx = [], [], [], []
    for r in rows:
        kept = [i for i, g in enumerate(r['grades']) if g is not None]
        for i in kept:
            X.append([*r['lanes'][i], r['reranker'][i]])
            y.append(1.0 if r['grades'][i] == 2 else 0.0)
            qid.append(r['id'])
        idx.append(kept)
    return np.array(X).reshape(-1, 5), np.array(y), np.array(qid), idx


def choose_model(logistic_loss, boosted_loss):
    """Protocol: pick the lower CV log loss; a tie within TIE_BAND prefers the logistic model (fewer assumptions,
    directly comparable to the frozen baseline's monotonicity guarantee).
    """
    if boosted_loss < logistic_loss - TIE_BAND:
        return 'boosted'
    return 'logistic'


def cross_validate_n(X, y, qid, seed=0, k=5):
    """Grouped-by-question k-fold CV log loss for both candidate models, refitting scaler/model inside each fold.
    Returns (logistic_losses, boosted_losses), each a list of k per-fold log losses.
    """
    folds = fit2.grouped_folds(qid, k=k, seed=seed)
    logistic_losses, boosted_losses = [], []
    for val_idx in folds:
        train_idx = np.setdiff1d(np.arange(len(y)), val_idx)
        scaler = fitn.MatrixScaler.fit(X[train_idx])
        Xz_train, Xz_val = scaler.apply(X[train_idx]), scaler.apply(X[val_idx])
        w_train = cal_run.question_weights(qid[train_idx])
        w_val = cal_run.question_weights(qid[val_idx])

        logistic = fitn.fit_monotonic_logistic_n(Xz_train, y[train_idx], l2=L2, weight=w_train)
        p_log = logistic.predict_proba(Xz_val)
        logistic_losses.append(fit2.log_loss(y[val_idx], p_log, weight=w_val))

        boosted = fitn.fit_gradient_boosted(Xz_train, y[train_idx], sample_weight=w_train, seed=seed)
        p_boost = boosted.predict_proba(Xz_val)[:, 1]
        boosted_losses.append(fit2.log_loss(y[val_idx], p_boost, weight=w_val))
    return logistic_losses, boosted_losses


def run_fit():
    verify(wide.read(rich.OUT / 'identity.json')['sha256'])
    train_rows = rich.rows('train')
    X, y, qid, _ = build_feature_matrix(train_rows)
    logistic_losses, boosted_losses = cross_validate_n(X, y, qid)
    mean_log, mean_boost = float(np.mean(logistic_losses)), float(np.mean(boosted_losses))
    chosen = choose_model(mean_log, mean_boost)

    scaler = fitn.MatrixScaler.fit(X)
    Xz = scaler.apply(X)
    w_all = cal_run.question_weights(qid)
    logistic_full = fitn.fit_monotonic_logistic_n(Xz, y, l2=L2, weight=w_all)
    boosted_full = fitn.fit_gradient_boosted(Xz, y, sample_weight=w_all, seed=0)
    mono_ok = {i: fitn.partial_dependence_is_monotonic(boosted_full, Xz[:50], i) for i in range(5)}

    out = {
        'scope': 'Grouped 5-fold CV on the train split (72 questions), comparing a 5-input monotonic logistic model '
                 'against HistGradientBoostingClassifier. Frozen 2-feature baseline for comparison: CV log loss '
                 '0.628 (recorded in docs/ANSWER_FOCUS_CALIBRATION_RESULTS.md), null 0.656.',
        'rows': len(y), 'questions': len(np.unique(qid)), 'l2': L2, 'tie_band': TIE_BAND,
        'cv_logistic_log_loss_mean': round(mean_log, 4), 'cv_logistic_log_loss_per_fold': logistic_losses,
        'cv_boosted_log_loss_mean': round(mean_boost, 4), 'cv_boosted_log_loss_per_fold': boosted_losses,
        'chosen_model': chosen,
        'scaler': {'mean': scaler.mean.tolist(), 'std': scaler.std.tolist()},
        'logistic_model': {'weights': logistic_full.weights.tolist(), 'intercept': logistic_full.intercept},
        'boosted_model_monotonic_per_feature': {
            ['dense', 'sparse', 'colbert', 'genome', 'bge_logit'][i]: ok for i, ok in mono_ok.items()},
        'source_sha256': manifest([Path(__file__), Path(fitn.__file__), Path(rich.__file__),
                                  ROOT / 'docs/ANSWER_FOCUS_RICHER_INPUTS_PROTOCOL.md',
                                  *sorted((rich.OUT / 'queries/train').glob('*.json'))]),
    }
    save_new('models.json', out)
    import joblib
    joblib.dump(boosted_full, OUT / 'boosted_model.joblib')
    print(f'logistic CV loss: {mean_log:.4f} {logistic_losses}')
    print(f'boosted  CV loss: {mean_boost:.4f} {boosted_losses}')
    print(f'chosen: {chosen}')
    if not all(mono_ok.values()):
        non_mono = [k for k, v in mono_ok.items() if not v]
        print(f'WARNING: boosted model is non-monotonic on features {[["dense","sparse","colbert","genome","bge_logit"][i] for i in non_mono]}')


def run_calibrate():
    models = wide.read(OUT / 'models.json')
    verify(models['source_sha256'])
    scaler = fitn.MatrixScaler(mean=np.array(models['scaler']['mean']), std=np.array(models['scaler']['std']))
    calibration_rows = rich.rows('calibration')

    def score_row(lanes_row, bge):
        x = scaler.apply(np.array([[*lanes_row, bge]]))
        if models['chosen_model'] == 'logistic':
            w = np.array(models['logistic_model']['weights'])
            return float(w @ x[0] + models['logistic_model']['intercept'])  # pre-sigmoid logit
        import joblib
        boosted = joblib.load(OUT / 'boosted_model.joblib')
        p = boosted.predict_proba(x)[0, 1]
        return float(np.log(p / (1 - p)))  # convert probability back to a logit for Platt, same as the 2-feature path

    grades_path = cal_run.OUT / 'grades.json'
    assert grades_path.exists(), f'expected the frozen calibration grades at {grades_path}'
    compiled = wide.read(grades_path)
    sheet = wide.read(cal_run.OUT / 'review-sheet.json')
    old_grades = {(row['question_id'], row['verse_id']): compiled['items'][row['item']]['grade'] for row in sheet}

    logits, labels, weights = [], [], []
    rows_by_q = {}
    for row in sheet:
        rows_by_q.setdefault(row['question_id'], []).append(row)
    lanes_by_q = {r['id']: r for r in calibration_rows}
    for qid_, rows in rows_by_q.items():
        q_weight = 1.0 / sum(1.0 / r['inclusion_probability'] for r in rows)
        lr = lanes_by_q[qid_]
        cand_pos = {v: i for i, v in enumerate(lr['candidates'])}
        for row in rows:
            v = row['verse_id']
            if v not in cand_pos:
                continue  # this candidate fell outside the 200-row pool this run captured lanes for
            i = cand_pos[v]
            z = score_row(lr['lanes'][i], lr['reranker'][i])
            logits.append(z)
            labels.append(1.0 if old_grades[(qid_, v)] == 2 else 0.0)
            weights.append(q_weight / row['inclusion_probability'])
    logits, labels, weights = np.array(logits), np.array(labels), np.array(weights)
    platt = fit2.fit_platt(logits, labels, weights)
    probs = platt.apply(logits)
    cutoff, f1 = fit2.choose_cutoff(probs, labels, weights)
    out = {'scope': f'Platt + cutoff for the chosen {models["chosen_model"]} model, same 120-row calibration sample '
                    'and grades as the frozen 2-feature model (no new review).',
           'chosen_model': models['chosen_model'], 'rows': len(labels),
           'platt': {'slope': platt.slope, 'intercept': platt.intercept}, 'cutoff': cutoff, 'f1_at_cutoff': f1,
           'source_sha256': manifest([OUT / 'models.json', Path(__file__)])}
    save_new('calibration.json', out)
    print(f'{models["chosen_model"]}: Platt slope={platt.slope:.4f} intercept={platt.intercept:.4f}; '
          f'cutoff={cutoff:.2f} (F1={f1:.4f}) on {len(labels)} calibration rows')


def _method6_scores(models, r):
    """z (pre-sigmoid logit) and the candidate order (best first) for one test row."""
    scaler = fitn.MatrixScaler(mean=np.array(models['scaler']['mean']), std=np.array(models['scaler']['std']))
    X = scaler.apply(np.array([[*lanes, bge] for lanes, bge in zip(r['lanes'], r['reranker'])]))
    if models['chosen_model'] == 'logistic':
        w, b = np.array(models['logistic_model']['weights']), models['logistic_model']['intercept']
        z = X @ w + b
    else:
        import joblib
        boosted = joblib.load(OUT / 'boosted_model.joblib')
        p = boosted.predict_proba(X)[:, 1]
        z = np.log(np.clip(p, 1e-9, 1 - 1e-9) / np.clip(1 - p, 1e-9, 1))
    return z, np.argsort(-z)


def method6_top5(models, test_rows):
    """Unfiltered: ranks each test question's 200 candidates by the chosen model's score; always exactly 5 shown."""
    out = {}
    for r in test_rows:
        _, order = _method6_scores(models, r)
        out[r['id']] = [r['candidates'][i] for i in order[:5]]
    return out


def method6b_top5_cutoff(models, calibration, test_rows):
    """Filtered by the frozen calibration's Platt + cutoff: variable length, can abstain entirely (method 4's
    counterpart for the richer-inputs model)."""
    platt = fit2.Platt(**calibration['platt'])
    cutoff = calibration['cutoff']
    out = {}
    for r in test_rows:
        z, order = _method6_scores(models, r)
        probs = platt.apply(z)
        out[r['id']] = [r['candidates'][i] for i in order if probs[i] >= cutoff][:5]
    return out


def run_test_new_items():
    """Lists any method-6 top-5 passage not already graded by the frozen baseline's test-topfive-grades.json, so
    they can be pooled into their own blind-review file before scoring (protocol: new passages need their own
    review; reusing the existing compiled grades for a ranking that surfaces different passages would otherwise
    silently leave them out of the denominator rather than actually judged).
    """
    models = wide.read(OUT / 'models.json')
    verify(models['source_sha256'])
    test_rows = rich.rows('test')
    top5 = method6_top5(models, test_rows)
    grades = wide.read(cal_run.OUT / 'test-topfive-grades.json')['items']
    graded_keys = {(item.rsplit(':', 1)[0], int(item.rsplit(':', 1)[1])) for item in grades}
    new_items = sorted({(qid_, v) for qid_, vs in top5.items() for v in vs if (qid_, v) not in graded_keys})
    save_new('method6-new-items.json', {'items': [f'{q}:{v}' for q, v in new_items]})
    print(f'{len(new_items)} new passages in method 6 top-5 need a blind review (not in the existing grades):')
    for q, v in new_items:
        print(f'  {q}:{v}')


def run_test_report():
    """Scores method 6 (the chosen richer-inputs model) against the frozen baseline's recorded test-report numbers.
    Requires new-item grades to already be compiled into method6-new-grades.json (fill in grade/reason per item
    listed by `test-new-items`, blind to method/rank/score, same as every prior review in this research line).
    """
    models = wide.read(OUT / 'models.json')
    calibration = wide.read(OUT / 'calibration.json')
    verify(models['source_sha256'])
    verify(calibration['source_sha256'])
    test_rows = rich.rows('test')
    methods = {'richer_unfiltered': method6_top5(models, test_rows),
              'richer_plus_cutoff': method6b_top5_cutoff(models, calibration, test_rows)}

    baseline_grades = wide.read(cal_run.OUT / 'test-topfive-grades.json')['items']
    by_key = {}
    for item, g in baseline_grades.items():
        qid_, v = item.rsplit(':', 1)
        by_key[(qid_, int(v))] = g['grade']
    new_grades_path = OUT / 'method6-new-grades.json'
    if new_grades_path.exists():
        new_grades = wide.read(new_grades_path)
        for it in new_grades['items']:
            qid_, v = it['item'].rsplit(':', 1)
            assert it['grade'] in (0, 1, 2) and it['reason'].strip(), f'ungraded: {it["item"]}'
            by_key[(qid_, int(v))] = it['grade']
    # the cutoff-filtered method must never need a grade the unfiltered method didn't already need (it only ever
    # removes candidates from the unfiltered ranking, never adds one) -- checked, not assumed
    for qid_, displayed in methods['richer_plus_cutoff'].items():
        for v in displayed:
            assert (qid_, v) in by_key, f'unexpected new passage from the filtered method: {qid_}:{v}'

    def grade_fn(qid_, v):
        return by_key.get((qid_, v))

    cal_rows = {r['id']: r for r in cal_run.cal.rows('test')}
    out = {'scope': f'Method 6: 5-input {models["chosen_model"]} model, same test split and fixed-slot scoring as '
                    'the frozen baseline (docs/ANSWER_FOCUS_CALIBRATION_RESULTS.md). New top-5 passages the '
                    'unfiltered ranking surfaced were pooled and blind-reviewed separately before this ran.',
          'chosen_model': models['chosen_model'], 'methods': {}}
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
        print(f"{name:20s} direct_p5={s['direct_p5_mean']:.3f} related_p5={s['related_p5_mean']:.3f} "
              f"any_direct={s['any_direct_rate']:.3f} mean_shown={s['mean_displayed']:.1f} "
              f"absent_counts={s['absent_question_result_counts']}")
    print('\nFrozen baseline (docs/ANSWER_FOCUS_CALIBRATION_RESULTS.md), for comparison:')
    print('  answer_focus_today_k10  direct_p5=0.350 related_p5=0.550 any_direct=0.625 absent_counts={test-phone-model: 5, test-rice-protein: 5}')
    print('  learned_unfiltered      direct_p5=0.350 related_p5=0.625 any_direct=0.750 absent_counts={test-phone-model: 5, test-rice-protein: 5}')
    print('  learned_plus_cutoff     direct_p5=0.350 related_p5=0.550 any_direct=0.750 absent_counts={test-phone-model: 0, test-rice-protein: 0}')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('action', choices=('fit', 'calibrate', 'test-new-items', 'test-report'))
    {'fit': run_fit, 'calibrate': run_calibrate, 'test-new-items': run_test_new_items,
     'test-report': run_test_report}[p.parse_args().action]()
