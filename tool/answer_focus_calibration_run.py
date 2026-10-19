"""Orchestrates docs/ANSWER_FOCUS_CALIBRATION_PROTOCOL.md after inference (answer_focus_calibration_infer.py has run
all three splits). Fits the monotonic Compass/BGE combination on train, reports grouped cross-validation as a
diagnostic, and produces the calibration review sheet. Grading itself is a separate deliberate step (as in every
prior Answer Focus stage): this script never assigns a grade, only samples what needs one and reads what already
has one. Never imported by the app.

  python -I tool/answer_focus_calibration_run.py fit        # CV diagnostic + final train-fitted model -> model.json
  python -I tool/answer_focus_calibration_run.py sample      # calibration review sheet -> review-sheet.json
  python -I tool/answer_focus_calibration_run.py compile     # after review-decisions.json is filled in -> grades.json
  python -I tool/answer_focus_calibration_run.py calibrate   # Platt fit + cutoff selection on the graded sample -> calibration.json
"""
import argparse
import hashlib
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
import answer_focus_calibration_fit as fit  # noqa: E402
import answer_focus_calibration_infer as cal  # noqa: E402
import answer_focus_wide_pool as wide  # noqa: E402

# Preserve the original, ungraded Compass-order packet and over-regularized fit.
OUT = cal.OUT / 'review-v2'
L2 = 1.0  # docs/ANSWER_FOCUS_CALIBRATION_PROTOCOL.md: "L2 penalty 1 on the slopes"
BANDS = (('1-10', 1, 10), ('11-50', 11, 50), ('51-200', 51, 200))
PER_BAND = 5


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


def checked_model():
    info = wide.read(OUT / 'model.json')
    verify(info['source_sha256'])
    return info, fit.Scaler(**info['scaler']), fit.MonotonicLogistic(**info['model'])


def learned_order(row, scaler, model):
    c, b = scaler.apply(row['compass'], row['reranker'])
    z = model.w_compass*c + model.w_bge*b + model.intercept
    assert len(z) == 200 and np.isfinite(z).all()
    return sorted(range(len(z)), key=lambda i: (-float(z[i]), i))


def training_rows():
    """(compass, bge, grade==2 as 0/1, question_id) for every labeled candidate in the train split."""
    compass, bge, y, qid = [], [], [], []
    for r in cal.rows('train'):
        for c, b, g in zip(r['compass'], r['reranker'], r['grades']):
            if g is None:
                continue
            compass.append(c)
            bge.append(b)
            y.append(1.0 if g == 2 else 0.0)
            qid.append(r['id'])
    return np.array(compass), np.array(bge), np.array(y), np.array(qid)


def question_weights(qid):
    """1/(labeled rows for that question), so every question contributes total weight 1 regardless of how many of
    its candidates were historically labeled (an 18-labeled-candidate question must not outweigh a 10-labeled one).
    """
    counts = {q: np.sum(qid == q) for q in np.unique(qid)}
    return np.array([1.0 / counts[q] for q in qid])


def cross_validate(compass, bge, y, qid, seed=0, k=5):
    """Grouped-by-question k-fold: refits the scaler and model inside each fold (no leakage of validation-fold
    statistics into training). Returns per-fold held-out log loss; a diagnostic, not a selection criterion
    (the protocol fits only one final model configuration, on all of train).
    """
    folds = fit.grouped_folds(qid, k=k, seed=seed)
    losses, null_losses = [], []
    for val_idx in folds:
        train_idx = np.setdiff1d(np.arange(len(y)), val_idx)
        scaler = fit.Scaler.fit(compass[train_idx], bge[train_idx])
        c_tr, b_tr = scaler.apply(compass[train_idx], bge[train_idx])
        w_tr = question_weights(qid[train_idx])
        model = fit.fit_monotonic_logistic(c_tr, b_tr, y[train_idx], l2=L2, question_weight=w_tr)
        c_val, b_val = scaler.apply(compass[val_idx], bge[val_idx])
        w_val = question_weights(qid[val_idx])
        p_val = model.predict_proba(c_val, b_val)
        losses.append(fit.log_loss(y[val_idx], p_val, weight=w_val))
        prevalence = np.average(y[train_idx], weights=w_tr)
        null_losses.append(fit.log_loss(y[val_idx], np.full(len(val_idx), prevalence), weight=w_val))
    return losses, null_losses


def run_fit():
    verify(wide.read(cal.OUT / 'identity.json')['sha256'])
    compass, bge, y, qid = training_rows()
    cv_losses, null_losses = cross_validate(compass, bge, y, qid)
    scaler = fit.Scaler.fit(compass, bge)
    c_all, b_all = scaler.apply(compass, bge)
    w_all = question_weights(qid)
    model = fit.fit_monotonic_logistic(c_all, b_all, y, l2=L2, question_weight=w_all)
    out = {
        'scope': 'Diagnostic 5-fold grouped CV on the 72-question train split (refit per fold); the research model '
                 'below is fit once on all of train for offline research. No test labels were used anywhere in this step.',
        'l2': L2, 'rows': len(y), 'questions': len(np.unique(qid)),
        'cv_log_loss_per_fold': cv_losses, 'cv_log_loss_mean': float(np.mean(cv_losses)),
        'null_log_loss': float(np.mean(null_losses)), 'cv_null_log_loss_per_fold': null_losses,
        'objective': 'sum(question_weight * binary_log_loss) + 1 * sum(slopes_squared)',
        'source_sha256': manifest([Path(__file__), Path(fit.__file__), Path(cal.__file__),
                                  ROOT / 'docs/ANSWER_FOCUS_CALIBRATION_PROTOCOL.md', cal.QUESTIONS,
                                  cal.OUT / 'identity.json', cal.OUT / 'splits.json',
                                  *sorted((cal.OUT / 'queries/train').glob('*.json'))]),
        'scaler': {'compass_mean': scaler.compass_mean, 'compass_std': scaler.compass_std,
                   'bge_mean': scaler.bge_mean, 'bge_std': scaler.bge_std},
        'model': {'w_compass': model.w_compass, 'w_bge': model.w_bge, 'intercept': model.intercept},
    }
    save_new('model.json', out)
    print(f"CV log loss: {out['cv_log_loss_mean']:.4f} (null {out['null_log_loss']:.4f}), per fold {cv_losses}")
    print(f"Final model: w_compass={model.w_compass:.4f} w_bge={model.w_bge:.4f} intercept={model.intercept:.4f}")


def rank_band_sample(candidates, seed=0, bands=BANDS, per_band=PER_BAND):
    """candidates ranked best-first (rank == 1-based position). Samples up to `per_band` indices without replacement
    from each band, every item having equal inclusion probability within its band (band_size choose per_band), or
    takes every item in a band shorter than per_band (inclusion probability 1). Returns a list of
    {candidate, rank, band, inclusion_probability}, deterministic for a given seed.
    """
    rng = np.random.default_rng(seed)
    n = len(candidates)
    out = []
    for name, lo, hi in bands:
        idx = [i for i in range(n) if lo <= (i + 1) <= min(hi, n)]
        if not idx:
            continue
        k = min(per_band, len(idx))
        chosen = rng.choice(idx, size=k, replace=False)
        prob = k / len(idx)
        for i in sorted(chosen.tolist()):
            out.append({'candidate': candidates[i], 'rank': i + 1, 'band': name, 'inclusion_probability': prob})
    return out


def run_sample():
    """Writes the probability-sampled calibration review sheet (120 rows: 8 questions x up to 15 band samples)."""
    corpus = wide.Corpus()
    _, scaler, model = checked_model()
    rows_out = []
    for r in cal.rows('calibration'):
        seed = int(hashlib.sha256(f'20261018:{r["id"]}'.encode()).hexdigest(), 16) % (2**32)
        order = learned_order(r, scaler, model)
        sample = rank_band_sample([r['candidates'][i] for i in order], seed=seed)
        for s in sample:
            v = s['candidate']
            i = order[s['rank'] - 1]
            rows_out.append({
                'item': f'{r["id"]}:{v}', 'question_id': r['id'], 'query': r['query'], 'verse_id': v,
                'reference': corpus.ref(v), 'rank': s['rank'], 'band': s['band'], 'seed': seed,
                'inclusion_probability': s['inclusion_probability'],
                'compass_score': r['compass'][i], 'reranker_logit': r['reranker'][i],
                'context': [{'reference': corpus.ref(u), 'focal': u == v, 'text': t}
                           for u, t in corpus.window(v, r['language'])],
            })
    assert len(rows_out) == 120 and len({r['item'] for r in rows_out}) == 120
    save_new('review-sheet.json', rows_out)
    blind = [{k: r[k] for k in ('item', 'query', 'reference', 'context')} for r in rows_out]
    blind.sort(key=lambda r: hashlib.sha256(f"blind-v2:{r['item']}".encode()).hexdigest())
    save_new('blind-view.json', blind)
    hashes = manifest([OUT / 'model.json', OUT / 'review-sheet.json', OUT / 'blind-view.json',
                       *sorted((cal.OUT / 'queries/calibration').glob('*.json'))])
    save_new('review-manifest.json', hashes)
    save_new('review-decisions.json', {
        'source_sha256': hashes,
        'provenance': 'Fill in grade (0/1/2) and reason for every item below before running `compile`. Method, rank '
                      'and score must stay hidden: review only blind-view.json. Record reviewer identity and '
                      'whether review is independent or exploratory AI review. No existing grades are reused.',
        'reviewer': '', 'review_type': '',
        'items': [{'item': r['item'], 'grade': None, 'reason': ''} for r in blind],
    })
    print(f'{len(rows_out)} sampled (3 bands x up to 5, per calibration question); '
          '120 need a new blind review. Give the reviewer only blind-view.json and review-decisions.json.')


def validate_decisions(sheet, decisions):
    expected = {r['item'] for r in sheet}
    by = {d['item']: d for d in decisions['items']}
    assert len(expected) == len(sheet), 'Duplicate review item'
    assert len(by) == len(decisions['items']), 'Duplicate decision'
    assert set(by) == expected, 'Missing or extra decisions'
    assert decisions.get('reviewer', '').strip() and decisions.get('review_type', '').strip(), 'Identify reviewer and review type'
    for d in by.values():
        assert type(d['grade']) is int and d['grade'] in (0, 1, 2) and d['reason'].strip(), f"Missing/invalid decision: {d['item']}"
    return {key: {'grade': d['grade'], 'reason': d['reason']} for key, d in by.items()}


def run_compile():
    sheet = wide.read(OUT / 'review-sheet.json')
    decisions = wide.read(OUT / 'review-decisions.json')
    checked_model()
    assert decisions['source_sha256'] == wide.read(OUT / 'review-manifest.json'), 'Review packet mismatch'
    verify(decisions['source_sha256'])
    graded = validate_decisions(sheet, decisions)
    save_new('grades.json', {'provenance': decisions['provenance'], 'reviewer': decisions['reviewer'],
                            'review_type': decisions['review_type'], 'items': graded,
                            'source_sha256': manifest([OUT / 'review-decisions.json', OUT / 'review-manifest.json']),
                            'review_sha256': decisions['source_sha256']})
    print(f'Compiled {len(graded)} calibration-sample grades.')


def run_calibrate():
    sheet = wide.read(OUT / 'review-sheet.json')
    compiled = wide.read(OUT / 'grades.json')
    verify(compiled['source_sha256'])
    verify(compiled['review_sha256'])
    grades = compiled['items']
    model_info, scaler, model = checked_model()
    rows_by_q = {}
    for r in sheet:
        rows_by_q.setdefault(r['question_id'], []).append(r)
    logits, labels, weights = [], [], []
    for qid_, rows in rows_by_q.items():
        q_weight = 1.0 / sum(1.0/r['inclusion_probability'] for r in rows)
        for r in rows:
            g = grades[r['item']]['grade']
            c, b = scaler.apply(np.array([r['compass_score']]), np.array([r['reranker_logit']]))
            z = model.w_compass * c[0] + model.w_bge * b[0] + model.intercept  # pre-sigmoid ranking logit
            logits.append(z)
            labels.append(1.0 if g == 2 else 0.0)
            weights.append(q_weight / r['inclusion_probability'])
    logits, labels, weights = np.array(logits), np.array(labels), np.array(weights)
    platt = fit.fit_platt(logits, labels, weights)
    probs = platt.apply(logits)
    cutoff, f1 = fit.choose_cutoff(probs, labels, weights)
    out = {'scope': 'Platt scaling and cutoff fit on the 120-row probability-sampled calibration review, inverse-'
                    'inclusion-probability weighted, each question totaling weight 1. No final-test label was used.',
           'rows': len(labels), 'platt': {'slope': platt.slope, 'intercept': platt.intercept},
           'cutoff': cutoff, 'f1_at_cutoff': f1, 'weight_sum': float(weights.sum()),
           'reviewer': compiled['reviewer'], 'review_type': compiled['review_type'],
           'scaler': model_info['scaler'], 'model': model_info['model'],
           'source_sha256': manifest([OUT / 'grades.json', OUT / 'review-manifest.json',
                                      OUT / 'model.json', OUT / 'review-decisions.json']),
           'selection_counts': {r['id']: int(np.sum(fit.Platt(platt.slope, platt.intercept).apply(
               model.w_compass*scaler.apply(r['compass'], r['reranker'])[0] +
               model.w_bge*scaler.apply(r['compass'], r['reranker'])[1] + model.intercept) >= cutoff))
               for r in cal.rows('calibration')}}
    save_new('calibration.json', out)
    print(f'Platt: slope={platt.slope:.4f} intercept={platt.intercept:.4f}; cutoff={cutoff:.2f} (F1={f1:.4f})')


def method_results(row, scaler, model, platt, cutoff):
    """The five protocol methods' orderings/subsets for one 200-candidate row (docs/ANSWER_FOCUS_CALIBRATION_PROTOCOL.md
    "Final test and controls"). Returns {1: [...], 2: [...], 3: [...], 4: [...], 5: [...]}, each a list of candidate
    ids (methods 1-3 always length 5; methods 4-5 can be shorter, including empty).
    """
    candidates, compass, bge = row['candidates'], row['reranker'], None  # placeholder to keep lints quiet below
    bge = row['reranker']

    # 1. Current Answer Focus: BGE reorders only the Compass-order top 10; the rest stays in Compass order untouched.
    top10_idx = list(range(min(10, len(candidates))))
    bge_within_top10 = sorted(top10_idx, key=lambda i: (-bge[i], i))
    m1_order = bge_within_top10 + [i for i in range(len(candidates)) if i not in top10_idx]
    m1 = [candidates[i] for i in m1_order[:5]]

    # 2. BGE ordering of all 200, unfiltered.
    m2_order = sorted(range(len(candidates)), key=lambda i: (-bge[i], i))
    m2 = [candidates[i] for i in m2_order[:5]]

    # 3. Learned combination of all 200, unfiltered -- always exactly 5 (or fewer if the pool itself is shorter).
    learned = learned_order(row, scaler, model)
    m3 = [candidates[i] for i in learned[:5]]

    # 4. Learned combination + frozen calibrated cutoff: variable length, can be empty.
    c, b = scaler.apply(row['compass'], row['reranker'])
    z = model.w_compass * c + model.w_bge * b + model.intercept
    probs = platt.apply(z)
    m4_idx = [i for i in learned if probs[i] >= cutoff]
    m4 = [candidates[i] for i in m4_idx[:5]]

    # 5. BGE-above-mean, diagnostic control (the method whose audit (docs/RERANKER_STAGE2_RESULTS.md, the mean-cutoff
    # audit) motivated this whole calibration branch): candidates strictly above the pool's mean BGE score, by BGE order.
    mean_bge = float(np.mean(bge))
    above_mean = [i for i in m2_order if bge[i] > mean_bge]
    m5 = [candidates[i] for i in above_mean[:5]]

    return {1: m1, 2: m2, 3: m3, 4: m4, 5: m5}


def run_test_topfive():
    """Pools the union of all five methods' top-5 on the 10 test questions into a blind review packet. Test labels
    are never opened before this point in the protocol; this is the first time they are touched.
    """
    _, scaler, model = checked_model()
    calibration = wide.read(OUT / 'calibration.json')
    platt = fit.Platt(**calibration['platt'])
    cutoff = calibration['cutoff']
    corpus = wide.Corpus()
    rows_out, union_by_q = [], {}
    for r in cal.rows('test'):
        methods = method_results(r, scaler, model, platt, cutoff)
        union_by_q[r['id']] = methods
        for v in sorted({v for vs in methods.values() for v in vs}):
            rows_out.append({'item': f'{r["id"]}:{v}', 'question_id': r['id'], 'query': r['query'],
                             'verse_id': v, 'reference': corpus.ref(v),
                             'context': [{'reference': corpus.ref(u), 'focal': u == v, 'text': t}
                                        for u, t in corpus.window(v, r['language'])]})
    shuffled = sorted(rows_out, key=lambda r: hashlib.sha256(f'test-topfive:{r["item"]}'.encode()).hexdigest())
    save_new('test-topfive-sheet.json', rows_out)
    save_new('test-topfive-blind.json', [{k: r[k] for k in ('item', 'question_id', 'query', 'reference', 'context')}
                                         for r in shuffled])
    save_new('test-method-unions.json', union_by_q)
    hashes = manifest([OUT / 'model.json', OUT / 'calibration.json', OUT / 'test-topfive-sheet.json',
                       *sorted((cal.OUT / 'queries/test').glob('*.json'))])
    save_new('test-topfive-manifest.json', hashes)
    save_new('test-topfive-decisions.json', {
        'source_sha256': hashes,
        'provenance': 'Fill in grade (0/1/2) and reason for every item below before running `test-compile`. Review '
                      'only test-topfive-blind.json (method, rank and score hidden). This is the final-test review: '
                      'once compiled, these grades must not feed back into the model, calibration or cutoff above.',
        'reviewer': '', 'review_type': '',
        'items': [{'item': r['item'], 'grade': None, 'reason': ''} for r in shuffled],
    })
    print(f'{len(rows_out)} distinct top-5-union passages across the 10 test questions need a blind review.')


def run_test_compile():
    sheet = wide.read(OUT / 'test-topfive-sheet.json')
    decisions = wide.read(OUT / 'test-topfive-decisions.json')
    graded = validate_decisions(sheet, decisions)
    wide.write(OUT / 'test-topfive-grades.json', {'provenance': decisions['provenance'],
                                                  'source_sha256': manifest([OUT / 'test-topfive-decisions.json',
                                                                            OUT / 'test-topfive-manifest.json']),
                                                  'review_sha256': decisions['source_sha256'], 'items': graded})
    print(f'Compiled {len(graded)} final-test top-5-union grades.')


def run_test_whole_list():
    """Independent probability-sampled whole-list review per method, per protocol: up to 5 per rank band on EACH
    method's own ranking (methods 1/2/3/5 use their own order; method 4's variable-length output has no bands beyond
    what it returned, so it is sampled from its own list directly, capped at 5). Separate from the top-five pool.
    """
    _, scaler, model = checked_model()
    calibration = wide.read(OUT / 'calibration.json')
    platt = fit.Platt(**calibration['platt'])
    cutoff = calibration['cutoff']
    corpus = wide.Corpus()
    rows_out = []
    for r in cal.rows('test'):
        seed = int(hashlib.sha256(f'test-whole-list:{r["id"]}'.encode()).hexdigest(), 16) % (2**32)
        orderings = {
            1: [r['candidates'][i] for i in (list(range(min(10, len(r['candidates'])))) +
                                             [i for i in range(len(r['candidates'])) if i >= 10])],
            2: sorted(r['candidates'], key=lambda c: -r['reranker'][r['candidates'].index(c)]),
            3: [r['candidates'][i] for i in learned_order(r, scaler, model)],
        }
        for method_id, ranked in orderings.items():
            sample = rank_band_sample(ranked, seed=seed + method_id)
            for s in sample:
                v = s['candidate']
                rows_out.append({'item': f'{r["id"]}:m{method_id}:{v}', 'question_id': r['id'], 'method': method_id,
                                 'query': r['query'], 'verse_id': v, 'reference': corpus.ref(v),
                                 'rank': s['rank'], 'band': s['band'], 'inclusion_probability': s['inclusion_probability'],
                                 'context': [{'reference': corpus.ref(u), 'focal': u == v, 'text': t}
                                            for u, t in corpus.window(v, r['language'])]})
    unique = {r['item']: r for r in rows_out}.values()  # the same passage can be independently sampled by >1 method
    shuffled = sorted(unique, key=lambda r: hashlib.sha256(f'test-whole-list-blind:{r["item"]}'.encode()).hexdigest())
    save_new('test-whole-list-sheet.json', list(unique))
    save_new('test-whole-list-blind.json', [{k: r[k] for k in ('item', 'question_id', 'query', 'reference', 'context')}
                                            for r in shuffled])
    hashes = manifest([OUT / 'model.json', OUT / 'test-whole-list-sheet.json',
                       *sorted((cal.OUT / 'queries/test').glob('*.json'))])
    save_new('test-whole-list-manifest.json', hashes)
    save_new('test-whole-list-decisions.json', {
        'source_sha256': hashes,
        'provenance': 'Independent probability sample for whole-list precision/Brier/log-loss estimates, separate '
                      'from the top-five pool. Fill in grade (0/1/2) and reason for every item; review only '
                      'test-whole-list-blind.json.',
        'reviewer': '', 'review_type': '',
        'items': [{'item': r['item'], 'grade': None, 'reason': ''} for r in shuffled],
    })
    print(f'{len(unique)} distinct passages need a blind whole-list review '
          f'({len(rows_out)} method-band draws before de-duplication).')


def score_method(question_id, displayed_ids, grade_fn, slots=5):
    """Fixed-slot scoring for one question's displayed result list (protocol: "For fixed-slot P@5, missing results
    count as zero; also report precision among displayed results and answer coverage so abstention cannot create a
    misleading perfect score."). grade_fn(question_id, verse_id) -> 0/1/2/None (None = not yet judged).
    """
    graded = [grade_fn(question_id, v) for v in displayed_ids[:slots]]
    unjudged = sum(1 for g in graded if g is None)
    direct_shown = sum(1 for g in graded if g == 2)
    related_shown = sum(1 for g in graded if g is not None and g >= 1)
    return {
        'displayed': len(displayed_ids[:slots]),
        'unjudged': unjudged,
        'direct_p5': direct_shown / slots,  # FIXED denominator; missing slots (abstention or <5 shown) count as 0
        'related_p5': related_shown / slots,
        'direct_of_displayed': (direct_shown / len(graded)) if graded else None,  # None, not 0 or 1: undefined on abstention
        'any_direct': direct_shown > 0,
    }


def run_test_report():
    """Scores the five protocol methods on the 10 test questions' fixed-slot top-5 (missing = 0), using the compiled
    final-test grades. This is the FIRST point any test-split quality number is computed; the model, calibration and
    cutoff above were all frozen before this ran.
    """
    _, scaler, model = checked_model()
    calibration = wide.read(OUT / 'calibration.json')
    platt = fit.Platt(**calibration['platt'])
    cutoff = calibration['cutoff']
    grades = wide.read(OUT / 'test-topfive-grades.json')
    verify(grades['source_sha256'])
    corpus = wide.Corpus()
    by_key = {}
    for item, g in grades['items'].items():
        qid_, v = item.rsplit(':', 1)
        by_key[(qid_, int(v))] = g['grade']

    def grade_fn(qid_, v):
        return by_key.get((qid_, v))

    rows = cal.rows('test')
    method_names = {1: 'answer_focus_today_k10', 2: 'bge_full_pool_unfiltered', 3: 'learned_unfiltered',
                    4: 'learned_plus_cutoff', 5: 'bge_above_mean_control'}
    per_method = {m: [] for m in method_names}
    absent_counts = {m: {} for m in method_names}
    for r in rows:
        methods = method_results(r, scaler, model, platt, cutoff)
        for m, displayed in methods.items():
            scored = score_method(r['id'], displayed, grade_fn)
            scored['question_id'] = r['id']
            if r['kind'] == 'absent':
                absent_counts[m][r['id']] = scored['displayed']
            else:
                per_method[m].append(scored)

    out = {'scope': 'Final test: 10 held-out questions (8 answerable, 2 absent), labels opened only after the model, '
                    'Platt calibration and cutoff above were frozen. Fixed-slot P@5 counts missing/abstained slots '
                    'as zero. direct_of_displayed is precision among what was actually shown (None when nothing was '
                    'shown). This is one run on 8 answerable questions; treat the comparison as indicative, not a '
                    'confirmatory result -- see docs/ANSWER_FOCUS_CALIBRATION_PROTOCOL.md for the whole-list '
                    'sampling step still needed for a fuller estimate.',
           'methods': {}}
    for m, name in method_names.items():
        rows_m = per_method[m]
        out['methods'][name] = {
            'questions': len(rows_m),
            'direct_p5_mean': round(sum(r['direct_p5'] for r in rows_m) / len(rows_m), 4),
            'related_p5_mean': round(sum(r['related_p5'] for r in rows_m) / len(rows_m), 4),
            'any_direct_rate': round(sum(r['any_direct'] for r in rows_m) / len(rows_m), 4),
            'mean_displayed': round(sum(r['displayed'] for r in rows_m) / len(rows_m), 2),
            'total_unjudged_slots': sum(r['unjudged'] for r in rows_m),
            'per_question': rows_m,
            'absent_question_result_counts': absent_counts[m],
        }
    wide.write(OUT / 'test-report.json', out)
    for name, s in out['methods'].items():
        print(f"{name:28s} direct_p5={s['direct_p5_mean']:.3f} related_p5={s['related_p5_mean']:.3f} "
              f"any_direct={s['any_direct_rate']:.3f} mean_shown={s['mean_displayed']:.1f} "
              f"absent_counts={s['absent_question_result_counts']}")
    if any(s['total_unjudged_slots'] for s in out['methods'].values()):
        print('\nWARNING: some displayed slots have no grade yet (counted as 0 in direct_p5 above, correctly per '
              'the protocol, but they should still be reviewed for a complete picture):')
        for name, s in out['methods'].items():
            if s['total_unjudged_slots']:
                print(f'  {name}: {s["total_unjudged_slots"]} unjudged slots')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('action', choices=('fit', 'sample', 'compile', 'calibrate', 'test-topfive', 'test-compile',
                                      'test-report', 'test-whole-list'))
    {'fit': run_fit, 'sample': run_sample, 'compile': run_compile, 'calibrate': run_calibrate,
     'test-topfive': run_test_topfive, 'test-compile': run_test_compile, 'test-report': run_test_report,
     'test-whole-list': run_test_whole_list}[p.parse_args().action]()
