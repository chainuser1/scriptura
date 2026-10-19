"""Checks for the final-test methods in tool/answer_focus_calibration_run.py (synthetic data, no real inference needed).
Run: .venv\\Scripts\\python.exe -I test/answer_focus_calibration_test_check.py
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tool'))
import answer_focus_calibration_fit as fit  # noqa: E402
import answer_focus_calibration_run as run  # noqa: E402

rng = np.random.default_rng(1)

# A synthetic 200-candidate row: Compass descending, BGE random, so the five methods can genuinely disagree.
row = {
    'candidates': list(range(1000, 1200)),
    'compass': list(np.linspace(2.0, 0.0, 200)),  # Compass's own descending order, as stored
    'reranker': rng.normal(0, 3, 200).tolist(),
}
scaler = fit.Scaler(0.0, 1.0, 0.0, 1.0)
model = fit.MonotonicLogistic(w_compass=0.2, w_bge=0.4, intercept=-0.5)
platt = fit.Platt(slope=2.0, intercept=0.0)
cutoff = 0.5

# ---- method_results: five orderings keyed 1..5 as in the protocol -----------------------------------------------------
results = run.method_results(row, scaler, model, platt, cutoff)
assert set(results) == {1, 2, 3, 4, 5}, set(results)

# Method 1 (current Answer Focus): BGE sorts only the first 10 Compass candidates; its top-5 must be a subset of the
# Compass-order top 10, i.e. candidates whose Compass rank (0-indexed) is < 10.
m1 = results[1]
compass_rank = {c: i for i, c in enumerate(row['candidates'])}
assert len(m1) == 5
assert all(compass_rank[c] < 10 for c in m1), 'method 1 must only ever promote from the Compass top 10'

# Method 2 (BGE over all 200): top-5 by reranker logit alone.
m2 = results[2]
bge_by_cand = dict(zip(row['candidates'], row['reranker']))
expected_m2 = sorted(row['candidates'], key=lambda c: -bge_by_cand[c])[:5]
assert m2 == expected_m2

# Method 3 (learned, unfiltered): top-5 by the learned score alone, always exactly 5 (no abstention).
m3 = results[3]
assert len(m3) == 5

# Method 4 (learned + frozen cutoff): a subset of method 3's full ranking, in the same relative order, but variable
# length -- must be empty when every candidate's calibrated probability is below the cutoff.
m4 = results[4]
assert len(m4) <= 5
no_results_platt = fit.Platt(slope=0.0, intercept=-10.0)  # forces every probability near 0
empty_check = run.method_results(row, scaler, model, no_results_platt, cutoff=0.9)
assert empty_check[4] == [], 'method 4 must be able to return nothing'

# Method 5 (BGE-above-mean, diagnostic control): a subset of candidates scoring strictly above the mean BGE score,
# capped to its own top 5 by BGE for the top-five comparison table.
m5 = results[5]
mean_bge = np.mean(row['reranker'])
assert all(bge_by_cand[c] > mean_bge for c in m5), 'method 5 must only keep above-mean BGE candidates'
assert len(m5) <= 5

# ---- whole_list_sample: independent rank-band sample on the LEARNED ranking, reusable band logic -----------------------
order = run.learned_order(row, scaler, model)
sample = run.rank_band_sample([row['candidates'][i] for i in order], seed=0)
assert len(sample) == 15  # 3 bands x 5, same shape as the calibration sampler

# ---- score_method: fixed-slot P@5 (missing = 0), precision-among-displayed, answer coverage ---------------------------
grade_fn = lambda qid_, v: {10: 2, 11: 1, 12: 0}.get(v)  # 3 of this question's results graded; 2 others unjudged
m = run.score_method('q1', [10, 11, 12], grade_fn)
assert m['direct_p5'] == 1 / 5, m  # 1 direct out of 5 FIXED slots (missing slots count as 0, matching the protocol)
assert m['displayed'] == 3
assert m['direct_of_displayed'] == 1 / 3  # precision among what was actually shown
assert m['any_direct'] is True

m_empty = run.score_method('q1', [], grade_fn)
assert m_empty['direct_p5'] == 0.0 and m_empty['displayed'] == 0 and m_empty['any_direct'] is False
# abstaining (0 results) must not look like perfect precision: direct_of_displayed is undefined (None), not 1.0 or 0.0
assert m_empty['direct_of_displayed'] is None

# an unjudged candidate must not silently count as a nonanswer
grade_unjudged = lambda qid_, v: None
m_unjudged = run.score_method('q1', [10], grade_unjudged)
assert m_unjudged['unjudged'] == 1 and m_unjudged['direct_p5'] == 0.0

print('answer_focus_calibration_test: all checks passed')
