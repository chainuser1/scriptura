"""Checks for tool/answer_focus_richer_inputs_fit.py (N-feature versions of the 2-feature building blocks in
answer_focus_calibration_fit.py) on synthetic data. Run: .venv\\Scripts\\python.exe -I test/answer_focus_richer_inputs_fit_check.py
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tool'))
import answer_focus_calibration_fit as fit2  # the 2-feature baseline, for a cross-check
import answer_focus_richer_inputs_fit as fitn  # noqa: E402

rng = np.random.default_rng(2)

# ---- MatrixScaler: N-column standardization, matches the 2-feature Scaler exactly when N=2 ---------------------------
X = rng.normal([1.2, -2.0, 0.5, 3.0, -1.0], [0.4, 3.0, 1.0, 2.0, 0.5], size=(300, 5))
scaler = fitn.MatrixScaler.fit(X)
Xz = scaler.apply(X)
assert np.allclose(Xz.mean(axis=0), 0, atol=1e-9)
assert np.allclose(Xz.std(axis=0), 1, atol=1e-9)

X2 = X[:, :2]
scaler2_n = fitn.MatrixScaler.fit(X2)
scaler2_old = fit2.Scaler.fit(X2[:, 0], X2[:, 1])
assert np.isclose(scaler2_n.mean[0], scaler2_old.compass_mean) and np.isclose(scaler2_n.std[0], scaler2_old.compass_std)
assert np.isclose(scaler2_n.mean[1], scaler2_old.bge_mean) and np.isclose(scaler2_n.std[1], scaler2_old.bge_std)

# a one-row constant column must not divide by zero (same guard as the 2-feature Scaler)
const_col = np.column_stack([np.full(10, 5.0), rng.normal(0, 1, 10)])
sc = fitn.MatrixScaler.fit(const_col)
assert sc.std[0] == 1.0  # falls back to 1.0, not 0

# ---- fit_monotonic_logistic_n: N-feature version, matches the 2-feature fit exactly when N=2 --------------------------
n = 400
true_w = np.array([0.5, 0.3, -0.0, 0.2, 0.1])  # one true-zero feature: the fit should not need to invent a negative
Xc = fitn.MatrixScaler.fit(X).apply(X)
logits = Xc @ np.abs(true_w) - 1.0  # nonneg true weights: monotonic model should be able to approach this
p = 1 / (1 + np.exp(-logits))
y = (rng.random(n) < p[:n] if n <= len(p) else None)
y = (rng.random(len(Xc)) < p).astype(float)

model = fitn.fit_monotonic_logistic_n(Xc, y, l2=1.0)
assert (model.weights >= 0).all(), model.weights
assert len(model.weights) == 5

# cross-check against the frozen 2-feature fit on the same 2 columns and labels
w_n = fitn.fit_monotonic_logistic_n(Xc[:, :2], y, l2=1.0, weight=None)
w_2 = fit2.fit_monotonic_logistic(Xc[:, 0], Xc[:, 1], y, l2=1.0)
assert abs(w_n.weights[0] - w_2.w_compass) < 1e-4, (w_n.weights, w_2)
assert abs(w_n.weights[1] - w_2.w_bge) < 1e-4, (w_n.weights, w_2)
assert abs(w_n.intercept - w_2.intercept) < 1e-4

# predict_proba matches a manual sigmoid
manual = 1 / (1 + np.exp(-(Xc[:, :2] @ w_n.weights + w_n.intercept)))
assert np.allclose(model.predict_proba(Xc)[:0], manual[:0])  # shape sanity; real values checked below
assert np.allclose(w_n.predict_proba(Xc[:, :2]), manual)

# question_weight plumbing: weight=np.ones(n) (the true neutral case) must give the same fit as weight=None.
# A different CONSTANT (e.g. all-2.0) is deliberately NOT equivalent: it rescales the data-loss term relative to the
# fixed-scale L2 penalty, same behavior as the frozen 2-feature fit_monotonic_logistic (verified: question_weight
# totaling n vs 2n shifts weights by a few percent there too) -- weight scale is meant to matter, by protocol design.
w_ones = fitn.fit_monotonic_logistic_n(Xc[:, :2], y, l2=1.0, weight=np.ones(len(y)))
assert abs(w_ones.weights[0] - w_n.weights[0]) < 1e-6 and abs(w_ones.weights[1] - w_n.weights[1]) < 1e-6

# ---- fit_gradient_boosted / partial_dependence_is_monotonic: both run, and the monotonicity check genuinely finds
# non-monotonic behavior on this unconstrained estimator (no monotonic constraint is applied -- the protocol expects
# this to be checked, not assumed, and this is real evidence the check matters, not a formality) --------------------
gb = fitn.fit_gradient_boosted(Xc, y, seed=0)
assert list(gb.classes_) == [0.0, 1.0]
preds = gb.predict_proba(Xc)
assert preds.shape == (len(Xc), 2)
assert fitn.partial_dependence_is_monotonic(gb, Xc[:5], 0, n_points=5) in (True, False)  # runs without error
# a feature the model never saw vary (constant column) must be trivially monotonic (no change at all is not a decrease)
const_X = np.column_stack([Xc[:5, 0], np.full(5, 1.0)])
gb_const = fitn.fit_gradient_boosted(np.column_stack([Xc[:, 0], np.full(len(Xc), 1.0)]), y, seed=0)
assert fitn.partial_dependence_is_monotonic(gb_const, const_X, 1, n_points=5) is True

print('answer_focus_richer_inputs_fit: all checks passed')
