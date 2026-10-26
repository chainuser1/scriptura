"""Tests for tool/trail_simulator.py. No pytest in this repo's tool/ -- plain assert-based test_* functions, run directly.

  .venv\\Scripts\\python.exe -I tool/test_trail_simulator.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
from trails import Trails  # noqa: E402
from trail_simulator import (AlwaysLikeReader, exploration_cost, flow_coherence,  # noqa: E402
                              mood_pull, novelty_spacing, play_trail, taste_convergence)

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


def test_exploration_cost_matches_known_explore_flags():
    run = [{'hits': [{'parts': {'explore': True}}, {'parts': {'explore': False}}]},
           {'hits': [{'parts': {'explore': False}}]}]
    assert exploration_cost(run) == 1 / 3


def test_taste_convergence_reports_none_when_threshold_never_crossed():
    # family 0 never exceeds a 50% share of any window up to size 10: it alternates with family 1 throughout,
    # starting with 1, so even a window of 1 never shows a bare majority of 0.
    run = [{'hits': [{'verse_id': i, 'dominant_family': (i + 1) % 2}]} for i in range(12)]
    assert taste_convergence(run, target_family=0, threshold=0.51, window=10) is None


def test_taste_convergence_counts_steps_for_an_always_like_reader():
    trails = Trails(str(RET))
    run = play_trail(trails, {'verse_id': 26137}, AlwaysLikeReader(), moods=[], k=5, focus=0.5, mood_strength=0.5, steps=20)
    target = trails.dominant[trails.row_of[26137]]
    result = taste_convergence(run, target_family=int(target))
    assert result is None or isinstance(result, int)


def test_flow_coherence_is_perfect_for_a_single_repeated_verse():
    trails = Trails(str(RET))
    run = [{'hits': [{'verse_id': 26137}]}, {'hits': [{'verse_id': 26137}]}, {'hits': [{'verse_id': 26137}]}]
    assert abs(flow_coherence(trails, run) - 1.0) < 1e-6


def test_flow_coherence_on_a_real_always_like_run_is_a_plausible_cosine():
    trails = Trails(str(RET))
    run = play_trail(trails, {'verse_id': 26137}, AlwaysLikeReader(), moods=[], k=5, focus=0.5, mood_strength=0.5, steps=10)
    fc = flow_coherence(trails, run)
    assert -1.0 <= fc <= 1.0


def test_novelty_spacing_finds_the_repeated_verse_pair():
    trails = Trails(str(RET))
    run = [{'hits': [{'verse_id': 26137}]}, {'hits': [{'verse_id': 1}]}, {'hits': [{'verse_id': 26137}]}]
    spacing = novelty_spacing(trails, run, cosine_threshold=0.90)
    assert 2 in spacing  # the two 26137 picks are 2 steps apart and trivially >= 0.90 cosine to themselves


def test_mood_pull_is_zero_or_handles_gracefully_with_no_mood():
    trails = Trails(str(RET))
    run = play_trail(trails, {'verse_id': 26137}, AlwaysLikeReader(), moods=[], k=5, focus=0.5, mood_strength=0.5, steps=5)
    assert mood_pull(trails, run, mood_vector=None) == 0.0  # no crash, no nonsensical ratio


def test_mood_pull_is_higher_with_a_mood_than_without():
    trails = Trails(str(RET))
    moods_data = json.loads((ROOT / 'assets' / 'trail_moods.json').read_text('utf-8'))['moods']
    comfort = next(m for m in moods_data if m['id'] == 'comfort')
    mv = trails.mood_vector([comfort['genes']])
    with_mood = play_trail(trails, {'verse_id': 26137}, AlwaysLikeReader(), moods=[comfort['genes']], k=5, focus=0.5, mood_strength=0.5, steps=20)
    without_mood = play_trail(trails, {'verse_id': 26137}, AlwaysLikeReader(), moods=[], k=5, focus=0.5, mood_strength=0.5, steps=20)
    assert mood_pull(trails, with_mood, mv) > mood_pull(trails, without_mood, mv)


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
            print(f'PASS {name}')
