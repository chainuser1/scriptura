"""Checks for tool/answer_focus_calibration_fit.py on synthetic data (no real inference files needed).
Run: .venv\\Scripts\\python.exe -I test/answer_focus_calibration_fit_check.py
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tool'))
import answer_focus_calibration_fit as fit  # noqa: E402

rng = np.random.default_rng(0)

# ---- fit_monotonic_logistic: coefficients must be nonnegative, loss must decrease vs. the intercept-only model -------
# The protocol fits on STANDARDIZED features (Scaler runs first in the real pipeline); an L2 penalty on raw, unscaled
# features would unfairly shrink whichever one happens to have the smaller raw magnitude, independent of real signal.
n = 400
compass_raw = rng.normal(1.2, 0.4, n)
bge_raw = rng.normal(-2, 3, n)
true_logit = 0.8 * (compass_raw - 1.2) / 0.4 + 0.3 * (bge_raw + 2) / 3 - 1.0  # true effect defined on standardized scale
p = 1 / (1 + np.exp(-true_logit))
y = (rng.random(n) < p).astype(float)
groups = rng.integers(0, 20, n)  # 20 "questions"

scaler0 = fit.Scaler.fit(compass_raw, bge_raw)
compass, bge = scaler0.apply(compass_raw, bge_raw)

model = fit.fit_monotonic_logistic(compass, bge, y, l2=1.0)
assert model.w_compass >= 0 and model.w_bge >= 0, (model.w_compass, model.w_bge)
assert model.w_compass > 0, 'the fit must preserve the predictive signal'

null_loss = fit.log_loss(y, np.full(n, y.mean()))
fitted_loss = fit.log_loss(y, model.predict_proba(compass, bge))
assert fitted_loss < null_loss, (fitted_loss, null_loss)

# Weak L2 on the same data approaches the unregularized optimum.
weak = fit.fit_monotonic_logistic(compass, bge, y, l2=0.001)
assert abs(weak.w_compass - 0.6277) < 0.01 and abs(weak.w_bge - 0.4514) < 0.01, (weak.w_compass, weak.w_bge)

# Independent scalar optimum: four balanced, perfectly separated observations.
# SUM loss derivative is -4/(1+exp(w)) + 2*w; mean loss would yield a different fit.
from scipy.optimize import brentq
cx = np.array([-1., -1., 1., 1.])
cy = np.array([0., 0., 1., 1.])
exact = brentq(lambda slope: -4/(1+np.exp(slope)) + 2*slope, 0, 2)
summed = fit.fit_monotonic_logistic(cx, np.zeros(4), cy, question_weight=np.ones(4))
assert abs(summed.w_compass - exact) < 1e-5, (summed.w_compass, exact)
# Repeating rows and halving their weights must leave the objective unchanged.
replicated = fit.fit_monotonic_logistic(np.repeat(cx, 2), np.zeros(8), np.repeat(cy, 2),
                                       question_weight=np.full(8, 0.5))
assert abs(replicated.w_compass - summed.w_compass) < 1e-8

# a feature with a true NEGATIVE relationship must not get a negative weight (the whole point of the constraint)
bad_bge = -bge  # flip sign: now higher "bge" means lower probability
model2 = fit.fit_monotonic_logistic(compass, bad_bge, y, l2=1.0)
assert model2.w_bge >= 0, 'monotonic constraint violated'

# ---- standardization: fit on train only, applied to other splits without peeking at their stats --------------------
scaler = fit.Scaler.fit(compass, bge)
assert abs(np.mean(scaler.apply(compass, bge)[0])) < 1e-9  # train data itself is mean-zero after scaling
other_compass = compass[:10] + 5.0  # a shifted "calibration" set
scaled = scaler.apply(other_compass, bge[:10])[0]
assert not np.isclose(np.mean(scaled), 0), 'scaler must use train stats, not recompute per split'

# ---- grouped k-fold: every group appears in exactly one validation fold, no group split across folds ----------------
folds = fit.grouped_folds(groups, k=5, seed=0)
assert len(folds) == 5
seen = set()
for fold in folds:
    val_groups = set(groups[fold])
    assert not (val_groups & seen), 'a group appeared in more than one validation fold'
    seen |= val_groups
assert seen == set(groups.tolist())
all_val_idx = sorted(i for fold in folds for i in fold)
assert all_val_idx == list(range(n)), 'folds must partition every row exactly once'

# ---- Platt calibration: monotonic nonnegative slope, free intercept, inverse-probability weights ---------------------
logits = rng.normal(0, 2, 200)
true_p = 1 / (1 + np.exp(-(1.5 * logits - 0.5)))
labels = (rng.random(200) < true_p).astype(float)
weights = rng.uniform(0.5, 2.0, 200)
platt = fit.fit_platt(logits, labels, weights)
assert platt.slope >= 0
probs = platt.apply(logits)
assert np.all((probs >= 0) & (probs <= 1))
assert np.corrcoef(logits, probs)[0, 1] > 0.5, 'calibrated probability should track the ranking logit'

# ---- cutoff selection: weighted F1 over the 0.00..1.00 grid, ties choose the higher threshold ------------------------
probs_c = np.array([0.1, 0.2, 0.3, 0.6, 0.7, 0.9])
labels_c = np.array([0, 0, 1, 1, 0, 1])
w_c = np.ones(6)
cutoff, f1_at_cutoff = fit.choose_cutoff(probs_c, labels_c, w_c)
assert 0.0 <= cutoff <= 1.0
# a direct tie case: with no candidates landing strictly between 0.3 and 0.7, every threshold in that range gives the
# identical confusion matrix (and so identical F1) -> the tie-break must pick the highest of that tied range, 0.7
tied_probs = np.array([0.2, 0.8])
tied_labels = np.array([0, 1])
tied_w = np.ones(2)
c1, f1_tied = fit.choose_cutoff(tied_probs, tied_labels, tied_w, grid=np.array([0.3, 0.5, 0.7]))
assert c1 == 0.7, f'tie-break must pick the highest tied threshold, got {c1}'
assert f1_tied == 1.0

print('answer_focus_calibration_fit: all checks passed')
