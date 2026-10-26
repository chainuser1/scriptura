"""Tests for tool/trail_simulator.py. No pytest in this repo's tool/ -- plain assert-based test_* functions, run directly.

  .venv\\Scripts\\python.exe -I tool/test_trail_simulator.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
from trails import Trails  # noqa: E402
from trail_simulator import AlwaysLikeReader, play_trail  # noqa: E402

RET = Path(r'C:\Users\jayky\AppData\Roaming\Scriptures\Scriptures\scriptura\engine-pack\retrieval')


def test_always_like_reader_is_deterministic():
    trails = Trails(str(RET))
    reader = AlwaysLikeReader()
    seed = {'verse_id': 26137}  # John 3:16, same fixture trail_review_sheet.py already uses
    run1 = play_trail(trails, seed, reader, moods=[], k=5, focus=0.5, mood_strength=0.5, steps=12)
    run2 = play_trail(trails, seed, reader, moods=[], k=5, focus=0.5, mood_strength=0.5, steps=12)
    assert [r['verse_id'] for step in run1 for r in step['hits']] == [r['verse_id'] for step in run2 for r in step['hits']]


def test_invalid_action_from_a_reader_raises_loudly():
    trails = Trails(str(RET))

    class BadReader:
        def next_action(self, hits, events):
            return 'maybe'

    try:
        play_trail(trails, {'verse_id': 26137}, BadReader(), moods=[], k=5, focus=0.5, mood_strength=0.5, steps=3)
        assert False, 'expected a ValueError for an unrecognized action'
    except ValueError:
        pass


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
            print(f'PASS {name}')
