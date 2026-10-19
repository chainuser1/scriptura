"""Checks for tool/answer_focus_richer_inputs_run.py data assembly and model-selection logic (synthetic data).
Run: .venv\\Scripts\\python.exe -I test/answer_focus_richer_inputs_run_check.py
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tool'))
import answer_focus_richer_inputs_run as run  # noqa: E402

rng = np.random.default_rng(4)

# ---- build_feature_matrix: [dense, sparse, colbert, genome, bge_logit], aligned row-for-row with labels ---------------
fake_row = {
    'id': 'q1', 'candidates': [10, 11, 12],
    'lanes': [[1.0, 2.0, 3.0, 4.0], [5.0, 6.0, 7.0, 8.0], [9.0, 10.0, 11.0, 12.0]],
    'reranker': [0.1, 0.2, 0.3],
    'grades': [2, 0, None],
}
X, y, qid, idx = run.build_feature_matrix([fake_row])
assert X.shape == (2, 5), X.shape  # only the 2 labeled rows (grade is not None)
assert list(X[0]) == [1.0, 2.0, 3.0, 4.0, 0.1]
assert list(X[1]) == [5.0, 6.0, 7.0, 8.0, 0.2]
assert list(y) == [1.0, 0.0]  # grade==2 -> 1, else 0 (matches the frozen 2-feature convention)
assert list(qid) == ['q1', 'q1']
assert idx == [[0, 1]]  # per-row list of which candidate-list positions were used, for traceability

# a row with every candidate unlabeled contributes nothing to X/y, but still gets an (empty) entry in idx
empty_row = {**fake_row, 'grades': [None, None, None]}
X_e, y_e, qid_e, idx_e = run.build_feature_matrix([empty_row])
assert X_e.shape == (0, 5)
assert idx_e == [[]]

# two rows: idx tracks each row's own kept positions separately
X2, y2, qid2, idx2 = run.build_feature_matrix([fake_row, empty_row])
assert X2.shape == (2, 5) and idx2 == [[0, 1], []]

# ---- choose_model: picks by CV log loss; ties (within 0.01) prefer the logistic model (protocol rule) ----------------
assert run.choose_model(logistic_loss=0.60, boosted_loss=0.55) == 'boosted'
assert run.choose_model(logistic_loss=0.60, boosted_loss=0.61) == 'logistic'
assert run.choose_model(logistic_loss=0.60, boosted_loss=0.595) == 'logistic'  # within 0.01 -> prefer logistic
assert run.choose_model(logistic_loss=0.60, boosted_loss=0.589) == 'boosted'  # just outside the tie band

print('answer_focus_richer_inputs_run: all checks passed')
