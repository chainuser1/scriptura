"""Plays synthetic "readers" through Trails' real scoring (tool/trails.py) to measure properties of the
resulting stream -- taste convergence, flow, novelty spacing, exploration cost, mood pull -- so tuning is
measured, not argued (docs/superpowers/specs/2026-10-25-trails-next-move-design.md, section 3).

  .venv\\Scripts\\python.exe -I tool/trail_simulator.py
"""
from pathlib import Path

VALID_ACTIONS = {'like', 'skip', 'dislike'}


class AlwaysLikeReader:
    def next_action(self, hits, events):
        return 'like'


class AlwaysDislikeReader:
    def next_action(self, hits, events):
        return 'dislike'


class MixedPatternReader:
    """Same like/skip/like/dislike cadence tool/trail_review_sheet.py's own play() hardcodes, as a reusable reader."""
    PATTERN = ['like', 'skip', 'like', 'dislike']

    def __init__(self):
        self._i = 0

    def next_action(self, hits, events):
        a = self.PATTERN[self._i % len(self.PATTERN)]
        self._i += 1
        return a


def play_trail(trails, seed, reader, moods, *, k, focus, mood_strength, steps):
    """Plays [steps] cards of a trail against the real Trails.trail_next(), feeding [reader]'s chosen action back
    into the event log each time. Returns the full list of per-step trail_next() responses (not just verse ids),
    so later callers can read hits[].parts for their own metrics."""
    events, history, run = [], [], []
    for step in range(steps):
        r = trails.trail_next({'k': k, 'step': step, 'seed': seed, 'events': events, 'recent': history[-5:],
                                'moods': moods, 'mood_strength': mood_strength, 'focus': focus})
        run.append(r)
        if not r['hits']:
            break
        v = r['hits'][0]['verse_id']
        history.append(v)
        events.append({'verse_id': v, 'action': 'shown'})
        action = reader.next_action(r['hits'], events)
        if action not in VALID_ACTIONS:
            raise ValueError(f'unrecognized action {action!r} from reader; must be one of {sorted(VALID_ACTIONS)}')
        events.append({'verse_id': v, 'action': action})
    return run


if __name__ == '__main__':
    import sys
    ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(ROOT / 'tool'))
    print('tool/trail_simulator.py: see tool/test_trail_simulator.py for usage; report CLI lands in a later task.')
