"""Tests for tool/trail_tuning_sweep.py. No pytest in this repo's tool/ -- plain assert-based test_* functions, run directly.

  .venv\\Scripts\\python.exe -I tool/test_trail_tuning_sweep.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
from trails import Trails  # noqa: E402
from trail_simulator import AlwaysLikeReader, play_trail  # noqa: E402
from trail_tuning_sweep import SEED, _measure, no_repeats, swept_constant  # noqa: E402

RET = Path(r'C:\Users\jayky\AppData\Roaming\Scriptures\Scriptures\scriptura\engine-pack\retrieval')


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
    run = play_trail(trails, SEED, AlwaysLikeReader(), moods=[], k=5, focus=0.5, mood_strength=0.5, steps=20)
    m = _measure(trails, run)
    assert m['no_repeats_ok'] is True
    assert no_repeats(run) is True
    # _measure's own 'no_repeats_ok' field is exactly what sweep()'s report uses to set 'flagged' -- confirm the
    # field exists and is boolean, so a reader of the report can trust 'flagged' reflects a real check, not a
    # placeholder always False.
    with swept_constant(trails_module, 'TASTE', 0.9):
        run2 = play_trail(trails, SEED, AlwaysLikeReader(), moods=[], k=5, focus=0.5, mood_strength=0.5, steps=20)
        m2 = _measure(trails, run2)
    assert isinstance(m2['no_repeats_ok'], bool)


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
            print(f'PASS {name}')
