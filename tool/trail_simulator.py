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


def exploration_cost(run):
    """Fraction of all picks across [run] (a play_trail() result) whose parts.explore flag was true."""
    flags = [h['parts']['explore'] for step in run for h in step['hits']]
    return sum(flags) / len(flags) if flags else 0.0


def taste_convergence(run, target_family, threshold=0.5, window=10):
    """Steps until [target_family]'s share of the last [window] picks' dominant_family crosses [threshold];
    None if the run never reaches it. Reads only the picked (first) hit of each step, matching how play_trail
    itself records the stream."""
    picks = [step['hits'][0]['dominant_family'] for step in run if step['hits']]
    for i in range(len(picks)):
        recent = picks[max(0, i - window + 1):i + 1]
        if recent.count(target_family) / len(recent) >= threshold:
            return i
    return None


def _shown_verses(run):
    return [step['hits'][0]['verse_id'] for step in run if step['hits']]


def flow_coherence(trails, run):
    """Mean cosine similarity between consecutive shown verses' genome vectors (trails.V rows are already
    L2-normalized, so a raw dot product IS the cosine -- see tool/similar_verses.py's own SimilarVerses.__init__)."""
    verses = _shown_verses(run)
    if len(verses) < 2:
        return 0.0
    sims = [float(trails.V[trails.row_of[a]] @ trails.V[trails.row_of[b]]) for a, b in zip(verses, verses[1:])]
    return sum(sims) / len(sims)


def novelty_spacing(trails, run, cosine_threshold=0.90):
    """For every pair of shown verses whose genome cosine exceeds [cosine_threshold], the number of steps between
    them (by position in the shown-verse list, matching how 'recent' is tracked in a real trail)."""
    verses = _shown_verses(run)
    spacing = []
    for i in range(len(verses)):
        for j in range(i + 1, len(verses)):
            cos = float(trails.V[trails.row_of[verses[i]]] @ trails.V[trails.row_of[verses[j]]])
            if cos >= cosine_threshold:
                spacing.append(j - i)
    return spacing


def play_trail(trails, seed, reader, moods, *, k, focus, mood_strength, steps):
    """Plays [steps] cards of a trail against the real Trails.trail_next(), feeding [reader]'s chosen action back
    into the event log each time. Returns the full list of per-step trail_next() responses (not just verse ids),
    so later callers can read hits[].parts for their own metrics. Each hit also gets a 'dominant_family' key
    (trails.dominant[row], not part of the real engine response) so taste_convergence() can read it without
    needing a Trails object of its own."""
    events, history, run = [], [], []
    for step in range(steps):
        r = trails.trail_next({'k': k, 'step': step, 'seed': seed, 'events': events, 'recent': history[-5:],
                                'moods': moods, 'mood_strength': mood_strength, 'focus': focus})
        for h in r['hits']:
            row = trails.row_of.get(h['verse_id'])
            h['dominant_family'] = int(trails.dominant[row]) if row is not None else None
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
