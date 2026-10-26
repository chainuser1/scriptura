"""Tests for tool/trail_tuning_sweep.py. No pytest in this repo's tool/ -- plain assert-based test_* functions, run directly.
Needs a real retrieval/ pack: set SCRIPTURA_RETRIEVAL -- see trail_simulator.py's own RET.

  .venv\\Scripts\\python.exe -I tool/test_trail_tuning_sweep.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
from trails import Trails  # noqa: E402
from trail_simulator import AlwaysLikeReader, play_trail, RET  # noqa: E402
from trail_tuning_sweep import SEED, _run_one, near_dislike_ok, no_repeats, swept_constant  # noqa: E402


def test_sweeping_a_constant_does_not_leak_into_the_next_run():
    import trails as trails_module
    original = trails_module.TASTE
    with swept_constant(trails_module, 'TASTE', 0.9):
        assert trails_module.TASTE == 0.9
    assert trails_module.TASTE == original


def test_a_swept_constant_value_is_checked_against_the_no_repeat_property_before_being_reported():
    import trails as trails_module
    trails = Trails(str(RET))
    # A real, unmodified run must satisfy no_repeats (trail_next's own seen-set guards this already).
    m = _run_one(trails, AlwaysLikeReader, 'no_mood')
    assert m['no_repeats_ok'] is True
    # _run_one's own 'no_repeats_ok'/'near_dislike_ok' fields are exactly what sweep()'s report uses to set
    # 'flagged' -- confirm both fields exist and are boolean, so a reader of the report can trust 'flagged'
    # reflects a real check, not a placeholder always False.
    with swept_constant(trails_module, 'TASTE', 0.9):
        m2 = _run_one(trails, AlwaysLikeReader, 'no_mood')
    assert isinstance(m2['no_repeats_ok'], bool)
    assert isinstance(m2['near_dislike_ok'], bool)


def test_no_repeats_actually_detects_a_broken_run_not_just_a_good_one():
    # A hand-built run with the same verse shown twice must be caught -- proving 'flagged' can actually become
    # True, not just stay False on every real run this sweep happens to produce today.
    broken = [{'hits': [{'verse_id': 1}]}, {'hits': [{'verse_id': 2}]}, {'hits': [{'verse_id': 1}]}]
    assert no_repeats(broken) is False


def test_near_dislike_ok_flags_a_shown_verse_too_close_to_an_earlier_dislike():
    trails = Trails(str(RET))
    # A realistic event log (shown, then reaction, per verse -- play_trail's own order): verse v is shown and
    # disliked, THEN v is shown again later -- that second showing is the same verse, trivially cosine 1.0 to
    # its own earlier dislike, and must be flagged.
    v = SEED['verse_id']
    run = [{'hits': [{'verse_id': v}]}, {'hits': [{'verse_id': v}]}]
    events = [{'verse_id': v, 'action': 'shown'}, {'verse_id': v, 'action': 'dislike'},
              {'verse_id': v, 'action': 'shown'}]
    assert near_dislike_ok(trails, run, events, cosine_threshold=0.90) is False


def test_run_one_reports_mood_pull_so_mood_mu_s_sweep_can_actually_be_judged():
    # MOOD_MU controls how strongly the stream pulls toward a mood -- mood_pull is the one property that
    # actually measures that. Without it in _run_one's own output, a MOOD_MU sweep can show picks changed but
    # never say whether the change moved the stream TOWARD or AWAY from the mood.
    trails = Trails(str(RET))
    m = _run_one(trails, AlwaysLikeReader, 'comfort')
    assert 'mood_pull' in m
    assert isinstance(m['mood_pull'], float)
    m_no_mood = _run_one(trails, AlwaysLikeReader, 'no_mood')
    assert m_no_mood['mood_pull'] == 0.0


def test_near_dislike_ok_is_true_with_no_dislikes():
    trails = Trails(str(RET))
    run = play_trail(trails, SEED, AlwaysLikeReader(), moods=[], k=5, focus=0.5, mood_strength=0.5, steps=5)
    assert near_dislike_ok(trails, run, events=[], cosine_threshold=0.90) is True


def test_near_dislike_ok_does_not_count_a_verse_disliked_after_it_was_shown_as_violating_itself():
    # A real trail always shows a verse, THEN the reader reacts to it (shown, then like/skip/dislike -- see
    # play_trail's own event order). Disliking a verse immediately after it's shown must not make that same
    # verse "too close to an earlier dislike" of ITSELF (trivially cosine 1.0) -- only a dislike recorded
    # strictly before a later shown verse counts as "earlier".
    trails = Trails(str(RET))
    v = SEED['verse_id']
    run = [{'hits': [{'verse_id': v}]}]
    events = [{'verse_id': v, 'action': 'shown'}, {'verse_id': v, 'action': 'dislike'}]
    assert near_dislike_ok(trails, run, events, cosine_threshold=0.90) is True


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
            print(f'PASS {name}')
