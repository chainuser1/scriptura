"""Learned Compass/BGE score combination and relevance calibration (docs/ANSWER_FOCUS_CALIBRATION_PROTOCOL.md).

Building blocks only (fit_monotonic_logistic, Scaler, grouped_folds, fit_platt, choose_cutoff); the orchestration
that runs cross-validation on the train split, reviews the calibration sample, fits Platt scaling and freezes a
cutoff lives in answer_focus_calibration_run.py once the calibration review is complete. Never imported by the app.
"""
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit


def log_loss(y, p, weight=None, eps=1e-12):
    """Mean (or weight-normalized) binary log loss. weight sums to len(y) if given unnormalized."""
    p = np.clip(p, eps, 1 - eps)
    terms = -(y * np.log(p) + (1 - y) * np.log(1 - p))
    if weight is None:
        return float(np.mean(terms))
    weight = np.asarray(weight, dtype=float)
    return float(np.sum(terms * weight) / np.sum(weight))


@dataclass
class MonotonicLogistic:
    """p(grade==2) = sigmoid(w_compass*compass + w_bge*bge + intercept), both weights constrained >= 0 at fit time."""
    w_compass: float
    w_bge: float
    intercept: float

    def predict_proba(self, compass, bge):
        z = self.w_compass * np.asarray(compass) + self.w_bge * np.asarray(bge) + self.intercept
        return expit(z)


def fit_monotonic_logistic(compass, bge, y, l2=1.0, question_weight=None):
    """Two-feature logistic regression for y (0/1, typically grade==2), L2 penalty `l2` on the two slopes only (never
    the intercept), slopes constrained nonnegative so the fit can never reward a lower retrieval score. compass and
    bge should already be standardized (see Scaler) before calling this. question_weight, if given, is a per-row
    weight (1/labeled_rows_in_question so every question totals weight 1). The objective is the SUM of weighted
    losses plus l2 * sum(slopes_squared), not the mean loss returned by the reporting helper log_loss.
    """
    compass, bge, y = np.asarray(compass, float), np.asarray(bge, float), np.asarray(y, float)
    w = np.ones(len(y)) if question_weight is None else np.asarray(question_weight, float)
    assert compass.shape == bge.shape == y.shape == w.shape and len(y)
    assert all(np.isfinite(a).all() for a in (compass, bge, y, w))
    assert np.isin(y, [0, 1]).all() and (w > 0).all() and l2 >= 0

    def objective(params):
        wc, wb, b = params
        z = wc * compass + wb * bge + b
        # Protocol: SUM of weighted losses, each question totaling weight one.
        # Averaging here would multiply the effective L2 by the question count.
        loss = np.dot(w, np.logaddexp(0, z) - y * z)
        penalty = l2 * (wc**2 + wb**2)
        residual = w * (expit(z) - y)
        gradient = np.array([residual @ compass + 2*l2*wc,
                             residual @ bge + 2*l2*wb, residual.sum()])
        return loss + penalty, gradient

    result = minimize(objective, x0=np.zeros(3), jac=True, method='L-BFGS-B',
                      bounds=[(0, None), (0, None), (None, None)])
    if not result.success or not np.isfinite(result.x).all():
        raise ValueError(f'Ranking fit failed: {result.message}')
    wc, wb, b = result.x
    return MonotonicLogistic(w_compass=float(wc), w_bge=float(wb), intercept=float(b))


@dataclass
class Scaler:
    """Global feature standardization: z = (x - mean) / std, fit once on training data, applied unchanged elsewhere."""
    compass_mean: float
    compass_std: float
    bge_mean: float
    bge_std: float

    @staticmethod
    def fit(compass, bge):
        compass, bge = np.asarray(compass, float), np.asarray(bge, float)
        cs, bs = compass.std(), bge.std()
        return Scaler(compass.mean(), cs if cs > 0 else 1.0, bge.mean(), bs if bs > 0 else 1.0)

    def apply(self, compass, bge):
        compass, bge = np.asarray(compass, float), np.asarray(bge, float)
        return (compass - self.compass_mean) / self.compass_std, (bge - self.bge_mean) / self.bge_std


def grouped_folds(groups, k=5, seed=0):
    """k index arrays into `groups` (len(groups) rows) for validation, grouped so every group's rows stay together
    in exactly one fold (question-level grouping: no row from a question leaks across train/validation within a fold).
    """
    groups = np.asarray(groups)
    unique = np.unique(groups)
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(unique))
    shuffled = unique[order]
    group_folds = np.array_split(shuffled, k)
    return [np.where(np.isin(groups, gf))[0] for gf in group_folds]


@dataclass
class Platt:
    """Monotonic Platt scaling: p = sigmoid(slope*logit + intercept), slope constrained >= 0."""
    slope: float
    intercept: float

    def apply(self, logits):
        z = self.slope * np.asarray(logits, float) + self.intercept
        return expit(z)


def fit_platt(logits, labels, weight=None):
    """Fits p(label==1) = sigmoid(slope*logit + intercept) with slope >= 0, weighted log loss (inverse-inclusion-
    probability weights for the probability-sampled calibration review, normalized by the caller so each question
    totals weight 1).
    """
    logits, labels = np.asarray(logits, float), np.asarray(labels, float)
    w = np.ones(len(labels)) if weight is None else np.asarray(weight, float)
    assert logits.shape == labels.shape == w.shape and len(labels)
    assert all(np.isfinite(a).all() for a in (logits, labels, w))
    assert np.isin(labels, [0, 1]).all() and len(np.unique(labels)) == 2 and (w > 0).all()
    w = w / w.sum()

    def objective(params):
        slope, intercept = params
        z = slope * logits + intercept
        residual = w * (expit(z) - labels)
        return np.dot(w, np.logaddexp(0, z) - labels * z), np.array([residual @ logits, residual.sum()])

    result = minimize(objective, x0=np.array([1.0, 0.0]), jac=True, method='L-BFGS-B', bounds=[(0, None), (None, None)])
    if not result.success or not np.isfinite(result.x).all():
        raise ValueError(f'Calibration fit failed: {result.message}')
    slope, intercept = result.x
    return Platt(slope=float(slope), intercept=float(intercept))


def choose_cutoff(probs, labels, weight, grid=None):
    """Threshold in `grid` (default 0.00..1.00 step 0.01) maximizing inverse-probability-weighted F1 for labels==1
    among probs >= threshold. Ties choose the higher threshold (prefers a tighter, more conservative cutoff).
    Returns (threshold, f1_at_threshold). A threshold with no predicted positives scores F1 = 0.
    """
    probs, labels, weight = np.asarray(probs, float), np.asarray(labels, float), np.asarray(weight, float)
    if grid is None:
        grid = np.round(np.arange(0, 1.0001, 0.01), 2)
    best_t, best_f1 = grid[0], -1.0
    for t in grid:
        pred = probs >= t
        tp = np.sum(weight[pred & (labels == 1)])
        fp = np.sum(weight[pred & (labels == 0)])
        fn = np.sum(weight[~pred & (labels == 1)])
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        if f1 >= best_f1:  # >=, so the LAST (highest) threshold with the best score wins on a tie
            best_t, best_f1 = t, f1
    return float(best_t), float(best_f1)
