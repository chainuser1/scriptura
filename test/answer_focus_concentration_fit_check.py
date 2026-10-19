"""Checks for the per-feature-constraint fitting extension in tool/answer_focus_concentration_fit.py (synthetic data).
Run: .venv\\Scripts\\python.exe -I test/answer_focus_concentration_fit_check.py
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tool'))
import answer_focus_concentration_fit as fitc  # noqa: E402
import answer_focus_richer_inputs_fit as fitn  # cross-check against the all-monotonic version  # noqa: E402

rng = np.random.default_rng(5)

# ---- fit_partially_monotonic: with every feature marked monotonic, must match fit_monotonic_logistic_n exactly -----
n = 400
X = rng.normal(0, 1, (n, 3))
true_logit = 0.6 * np.abs(X[:, 0]) + 0.3 * np.abs(X[:, 1]) - 0.2 * X[:, 2] - 0.5  # 3rd feature has a true NEGATIVE effect
p = 1 / (1 + np.exp(-true_logit))
y = (rng.random(n) < p).astype(float)

all_monotonic = fitc.fit_partially_monotonic(X, y, l2=1.0, monotonic=[True, True, True])
ref = fitn.fit_monotonic_logistic_n(X, y, l2=1.0)
assert np.allclose(all_monotonic.weights, ref.weights, atol=1e-5), (all_monotonic.weights, ref.weights)
assert abs(all_monotonic.intercept - ref.intercept) < 1e-5

# ---- with the 3rd feature unconstrained, the fit should find its TRUE negative weight instead of being forced to 0 -
free = fitc.fit_partially_monotonic(X, y, l2=1.0, monotonic=[True, True, False])
assert free.weights[0] >= 0 and free.weights[1] >= 0  # still constrained
assert free.weights[2] < -0.05, f'expected a real negative weight to be recoverable, got {free.weights[2]}'
# and it must fit the data at least as well as forcing that weight to be nonnegative (lower or equal loss)
def total_loss(model, X, y, l2, monotonic):
    z = X @ model.weights + model.intercept
    data_loss = np.sum(np.logaddexp(0, z) - y * z)
    penalty = l2 * sum(w**2 for w, m in zip(model.weights, monotonic))  # only constrained features penalized, matches fit
    return data_loss + penalty
loss_constrained = total_loss(all_monotonic, X, y, 1.0, [True, True, True])
loss_free = total_loss(free, X, y, 1.0, [True, True, False])
assert loss_free <= loss_constrained + 1e-6, (loss_free, loss_constrained)

# ---- predict_proba matches a manual sigmoid ------------------------------------------------------------------------
manual = 1 / (1 + np.exp(-(X @ free.weights + free.intercept)))
assert np.allclose(free.predict_proba(X), manual)

# ---- a monotonic flag list of the wrong length is rejected -----------------------------------------------------------
try:
    fitc.fit_partially_monotonic(X, y, l2=1.0, monotonic=[True, True])
    raise AssertionError('mismatched monotonic length must raise')
except (AssertionError, ValueError):
    pass

print('answer_focus_concentration_fit: all checks passed')
