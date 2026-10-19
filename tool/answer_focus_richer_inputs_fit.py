"""N-feature building blocks for docs/ANSWER_FOCUS_RICHER_INPUTS_PROTOCOL.md. The frozen 2-feature model and its
fitting machinery (answer_focus_calibration_fit.py) are untouched and remain the recorded comparison point; this
module is the 5-input (dense, sparse, colbert, genome, bge_logit) extension, same fitting discipline (standardize
on training data only, sum of weighted log loss + L2 on slopes only, slopes constrained nonnegative). Also wraps
scikit-learn's HistGradientBoostingClassifier as the non-linear comparison, per the protocol's model 3.
"""
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit


@dataclass
class MatrixScaler:
    """Per-column standardization for an (n_rows, n_features) matrix: z = (x - mean) / std, fit once, applied
    unchanged elsewhere. A zero-variance column falls back to std=1 (matches answer_focus_calibration_fit.Scaler).
    """
    mean: np.ndarray
    std: np.ndarray

    @staticmethod
    def fit(X):
        X = np.asarray(X, float)
        std = X.std(axis=0)
        std = np.where(std > 0, std, 1.0)
        return MatrixScaler(mean=X.mean(axis=0), std=std)

    def apply(self, X):
        return (np.asarray(X, float) - self.mean) / self.std


@dataclass
class MonotonicLogisticN:
    """p(grade==2) = sigmoid(X @ weights + intercept), every weight constrained >= 0 at fit time (no feature may be
    rewarded for being lower -- same anti-extrapolation reasoning as the frozen 2-feature model, extended to N).
    """
    weights: np.ndarray
    intercept: float

    def predict_proba(self, X):
        return expit(np.asarray(X, float) @ self.weights + self.intercept)


def fit_monotonic_logistic_n(X, y, l2=1.0, weight=None):
    """X: (n_rows, n_features), already standardized (see MatrixScaler). y: 0/1. weight: optional per-row weight
    (e.g. 1/labeled_rows_in_question so every question totals weight 1); None means every row weighs the same.
    Objective is the SUM of weighted log loss plus l2 * sum(weights_squared) on the feature weights only (never the
    intercept) -- matches answer_focus_calibration_fit.fit_monotonic_logistic's objective exactly when n_features=2.
    """
    X, y = np.asarray(X, float), np.asarray(y, float)
    n, k = X.shape
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

    bounds = [(0, None)] * k + [(None, None)]
    result = minimize(objective, x0=np.zeros(k + 1), jac=True, method='L-BFGS-B', bounds=bounds)
    if not result.success or not np.isfinite(result.x).all():
        raise ValueError(f'Ranking fit failed: {result.message}')
    return MonotonicLogisticN(weights=result.x[:k], intercept=float(result.x[k]))


def fit_gradient_boosted(X, y, sample_weight=None, max_depth=3, seed=0):
    """scikit-learn HistGradientBoostingClassifier, defaults except max_depth (protocol: capped at 3, not justified
    by 1,220 training rows to go deeper) and random_state. No monotonic constraint is applied (not available for
    this estimator in the installed scikit-learn version); the caller must check partial_dependence_is_monotonic
    before using this model for ranking, per the protocol.
    """
    from sklearn.ensemble import HistGradientBoostingClassifier
    X, y = np.asarray(X, float), np.asarray(y, float)
    model = HistGradientBoostingClassifier(max_depth=max_depth, random_state=seed)
    model.fit(X, y, sample_weight=sample_weight)
    return model


def partial_dependence_is_monotonic(model, X, feature_index, n_points=20):
    """True if increasing feature_index (holding every other feature at its training-data value, one row at a time)
    never decreases the model's predicted probability, for every row in X. A gradient-boosted model has no built-in
    monotonic constraint; this checks after the fact whether one emerged anyway, per the protocol's requirement to
    flag (not silently accept) a negative partial dependence on a retrieval signal before using the model for ranking.
    """
    X = np.asarray(X, float)
    lo, hi = X[:, feature_index].min(), X[:, feature_index].max()
    grid = np.linspace(lo, hi, n_points)
    for row in X:
        preds = []
        for v in grid:
            probe = row.copy()
            probe[feature_index] = v
            preds.append(model.predict_proba(probe.reshape(1, -1))[0, 1])
        if np.any(np.diff(preds) < -1e-9):
            return False
    return True
