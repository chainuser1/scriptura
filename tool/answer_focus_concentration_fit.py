"""Per-feature-constraint logistic fit for docs/ANSWER_FOCUS_KEYWORD_CONCENTRATION_PROTOCOL.md. The all-monotonic
5-feature model (answer_focus_richer_inputs_fit.fit_monotonic_logistic_n) is untouched and remains the recorded
comparison point; this adds the ability to leave specific features (here: concentration) unconstrained, since there
is no a priori reason to assume its sign before fitting.
"""
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit


@dataclass
class PartiallyMonotonicLogistic:
    """p(grade==2) = sigmoid(X @ weights + intercept). Features marked monotonic at fit time are constrained >= 0;
    others are free to take any sign.
    """
    weights: np.ndarray
    intercept: float
    monotonic: list

    def predict_proba(self, X):
        return expit(np.asarray(X, float) @ self.weights + self.intercept)


def fit_partially_monotonic(X, y, l2=1.0, weight=None, monotonic=None):
    """X: (n_rows, n_features), already standardized. y: 0/1. monotonic: list of n_features bools, True = constrained
    nonnegative (same anti-extrapolation reasoning as the fully-monotonic model), False = unconstrained. L2 penalty
    applies to every feature's weight regardless of its constraint (the penalty is about fit stability, not sign).
    weight: optional per-row weight, same convention as fit_monotonic_logistic_n (None = every row weighs the same).
    """
    X, y = np.asarray(X, float), np.asarray(y, float)
    n, k = X.shape
    assert monotonic is not None and len(monotonic) == k, f'monotonic must list exactly {k} flags, got {monotonic}'
    w = np.ones(n) if weight is None else np.asarray(weight, float)
    assert X.shape[0] == y.shape[0] == w.shape[0] and n
    assert np.isfinite(X).all() and np.isfinite(y).all() and np.isfinite(w).all()
    assert np.isin(y, [0, 1]).all() and (w > 0).all() and l2 >= 0

    def objective(params):
        weights, b = params[:k], params[k]
        z = X @ weights + b
        loss = np.dot(w, np.logaddexp(0, z) - y * z)
        penalty = l2 * np.sum(weights**2)
        residual = w * (expit(z) - y)
        grad_w = X.T @ residual + 2 * l2 * weights
        grad_b = residual.sum()
        return loss + penalty, np.concatenate([grad_w, [grad_b]])

    bounds = [(0, None) if m else (None, None) for m in monotonic] + [(None, None)]
    result = minimize(objective, x0=np.zeros(k + 1), jac=True, method='L-BFGS-B', bounds=bounds)
    if not result.success or not np.isfinite(result.x).all():
        raise ValueError(f'Ranking fit failed: {result.message}')
    return PartiallyMonotonicLogistic(weights=result.x[:k], intercept=float(result.x[k]), monotonic=list(monotonic))
