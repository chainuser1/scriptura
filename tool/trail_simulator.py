"""Plays synthetic "readers" through Trails' real scoring (tool/trails.py) to measure properties of the
resulting stream -- taste convergence, flow, novelty spacing, exploration cost, mood pull -- so tuning is
measured, not argued (docs/superpowers/specs/2026-10-25-trails-next-move-design.md, section 3).

Battery is verse seeds only (no question seeds): tool/trails.py's Trails.seed_vector() cannot encode text, and
the native engine exposes no op to return the genome it computes internally for a text seed -- see this plan's
own ledger for the investigation. Adding that requires a new engine op, out of this plan's scope.

  .venv\\Scripts\\python.exe -I tool/trail_simulator.py
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'local-benchmarks'
# No generated-artifacts/engine-pack exists in a fresh checkout (this repo's own build staging is not committed) --
# set SCRIPTURA_RETRIEVAL to a real retrieval/ directory (e.g. an installed app's own downloaded pack) to run this
# against real data without one. See this plan's own ledger for why.
RET = Path(os.environ.get('SCRIPTURA_RETRIEVAL', ROOT / 'generated-artifacts' / 'engine-pack' / 'retrieval'))

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
    """Fraction of the verses a reader actually SEES across [run] (hits[0] of each step -- the only one
    play_trail() shows; the rest of each step's k-sized response is that step's own unshown candidate list)
    whose parts.explore flag was true."""
    flags = [step['hits'][0]['parts']['explore'] for step in run if step['hits']]
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


def mood_pull(trails, run, mood_vector):
    """Mean cosine of the run's shown verses to [mood_vector] (trails.V rows are already L2-normalized, so a raw
    dot product is the cosine). Returns 0.0 when there is no mood vector or no shown verses, rather than raising
    -- there is nothing to measure a "pull" toward."""
    if mood_vector is None:
        return 0.0
    verses = _shown_verses(run)
    if not verses:
        return 0.0
    sims = [float(trails.V[trails.row_of[v]] @ mood_vector) for v in verses]
    return sum(sims) / len(sims)


def play_trail(trails, seed, reader, moods, *, k, focus, mood_strength, steps, _events_out=None):
    """Plays [steps] cards of a trail against the real Trails.trail_next(), feeding [reader]'s chosen action back
    into the event log each time. Returns the full list of per-step trail_next() responses (not just verse ids),
    so later callers can read hits[].parts for their own metrics. Each hit also gets a 'dominant_family' key
    (trails.dominant[row], not part of the real engine response) so taste_convergence() can read it without
    needing a Trails object of its own. [_events_out], if given a list, is extended in place with the full
    shown/like/skip/dislike event log this call produced -- an optional out-parameter for callers (like the
    tuning sweep's own dislike-exclusion check) that need to know which verses were disliked, without changing
    this function's own return shape for every existing caller."""
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
    if _events_out is not None:
        _events_out.extend(events)
    return run


SEEDS = [('John 3:16', {'verse_id': 26137}), ('Alma 32:21', {'verse_id': 34000})]
READERS = [('always_like', AlwaysLikeReader), ('always_dislike', AlwaysDislikeReader), ('mixed', MixedPatternReader)]


def _run_battery(trails, moods_data):
    scenarios = []
    for seed_name, seed in SEEDS:
        for reader_name, reader_cls in READERS:
            for mood in [None] + moods_data:
                mood_genes = [] if mood is None else [mood['genes']]
                run = play_trail(trails, seed, reader_cls(), moods=mood_genes, k=5, focus=0.5, mood_strength=0.5, steps=20)
                mv = trails.mood_vector(mood_genes) if mood_genes else None
                target = int(trails.dominant[trails.row_of[seed['verse_id']]])
                scenarios.append({
                    'seed': seed_name, 'reader': reader_name, 'mood': mood['id'] if mood else None,
                    'taste_convergence': taste_convergence(run, target_family=target),
                    'flow_coherence': flow_coherence(trails, run),
                    'novelty_spacing': novelty_spacing(trails, run),
                    'exploration_cost': exploration_cost(run),
                    'mood_pull': mood_pull(trails, run, mv),
                })
    return scenarios


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(ROOT / 'tool'))
    from trails import Trails  # noqa: E402

    if not RET.exists():
        sys.exit(f'retrieval pack not found at {RET}\n'
                  f'Set SCRIPTURA_RETRIEVAL to a real retrieval/ directory (e.g. an installed app\'s own '
                  f'downloaded engine-pack) -- see tool/trail_simulator.py\'s own module docstring.')
    trails = Trails(str(RET))
    moods_data = json.loads((ROOT / 'assets' / 'trail_moods.json').read_text('utf-8'))['moods']
    scenarios = _run_battery(trails, moods_data)
    OUT.mkdir(exist_ok=True)
    (OUT / 'trail-simulator-report.json').write_text(json.dumps(scenarios, indent=1), 'utf-8')
    print(f'-> {OUT / "trail-simulator-report.json"} ({len(scenarios)} scenarios)')
    for s in scenarios:
        print(f"{s['seed']:12s} {s['reader']:14s} mood={str(s['mood']):10s} "
              f"explore_cost={s['exploration_cost']:.3f} mood_pull={s['mood_pull']:+.3f}")
