"""Checks for tool/answer_focus_concentration_run.py data assembly (synthetic data).
Run: .venv\\Scripts\\python.exe -I test/answer_focus_concentration_run_check.py
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tool'))
import answer_focus_concentration_run as run  # noqa: E402

# ---- build_feature_matrix_6: [dense, sparse, colbert, genome, bge_logit, concentration], aligned with labels --------
fake_row = {
    'id': 'q1', 'candidates': [10, 11, 12],
    'lanes': [[1.0, 2.0, 3.0, 4.0], [5.0, 6.0, 7.0, 8.0], [9.0, 10.0, 11.0, 12.0]],
    'reranker': [0.1, 0.2, 0.3],
    'concentration': [0.9, 0.5, 0.2],
    'grades': [2, 0, None],
}
X, y, qid, idx = run.build_feature_matrix_6([fake_row])
assert X.shape == (2, 6), X.shape
assert list(X[0]) == [1.0, 2.0, 3.0, 4.0, 0.1, 0.9]
assert list(X[1]) == [5.0, 6.0, 7.0, 8.0, 0.2, 0.5]
assert list(y) == [1.0, 0.0]
assert list(qid) == ['q1', 'q1']
assert idx == [[0, 1]]

print('answer_focus_concentration_run: all checks passed')
