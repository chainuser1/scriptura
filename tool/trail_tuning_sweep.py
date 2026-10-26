"""Sweeps tool/trails.py's scoring constants and reports the measured property deltas against the current
shipped baseline, so tuning is informed by numbers rather than argued in advance
(docs/superpowers/specs/2026-10-25-trails-next-move-design.md, section 4).

Sweeps run against tool/trails.py (the Python reference), not the native engine: the constants are Rust `const`s
in the real engine, compiled in and not patchable per run. The native engine is only ever used (elsewhere, in
tool/trail_simulator.py's own battery) to produce the unmodified-baseline numbers this sweep compares against.

  .venv\\Scripts\\python.exe -I tool/trail_tuning_sweep.py
"""
import contextlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'local-benchmarks'

sys.path.insert(0, str(ROOT / 'tool'))
import trails as trails_module  # noqa: E402
from trail_simulator import (AlwaysDislikeReader, AlwaysLikeReader, MixedPatternReader, RET,  # noqa: E402
                              exploration_cost, flow_coherence, mood_pull, novelty_spacing, play_trail, taste_convergence)


@contextlib.contextmanager
def swept_constant(module, name, value):
    """Sets module.name to value for the duration of the block, restoring the original value on exit -- even if
    the block raises, so a crashed sweep run never leaves trails.py's globals mutated for the next one."""
    original = getattr(module, name)
    setattr(module, name, value)
    try:
        yield
    finally:
        setattr(module, name, original)


def no_repeats(run):
    """The v1 spec's own no-verse-repeats property (section 9): every ACTUALLY SHOWN verse (the first/picked hit
    of each step -- the only one play_trail() feeds back as 'shown', the rest of each step's hits are just that
    step's own candidate list) appears at most once across the trail."""
    verses = [step['hits'][0]['verse_id'] for step in run if step['hits']]
    return len(verses) == len(set(verses))


def near_dislike_ok(trails, run, events, cosine_threshold=0.90):
    """The v1 spec's own dislike-neighbour-exclusion property (section 9): no shown verse's genome cosine to any
    EARLIER-disliked verse should reach [cosine_threshold] (NEAR_DISLIKE's own real exclusion radius) -- this is
    the one property NEAR_DISLIKE's own sweep actually controls, and no_repeats alone can never catch a value
    that lets a too-similar (not identical) verse back in. 'Earlier' is strict: walking [events] in their real
    order (play_trail's own 'shown' then reaction order), a verse shown, then disliked, must not count as
    violating against its own just-recorded dislike -- only a dislike already seen in the log before a LATER
    'shown' event counts, matching trail_next's own `near` filter, which only ever excludes against dislikes
    already recorded when it scores a future pick."""
    disliked_so_far = []
    for e in events:
        if e['action'] == 'shown':
            s = e['verse_id']
            for d in disliked_so_far:
                if float(trails.V[trails.row_of[s]] @ trails.V[trails.row_of[d]]) >= cosine_threshold:
                    return False
        elif e['action'] == 'dislike':
            disliked_so_far.append(e['verse_id'])
    return True


CANDIDATES = {
    'TASTE': [0.1, 0.2, 0.3, 0.5, 0.8],
    'MOOD_MU': [0.2, 0.4, 0.6, 0.9, 1.2],
    'NOVELTY_BASE': [0.0, 0.05, 0.1, 0.2, 0.3],
    'NOVELTY_FOCUS': [0.1, 0.2, 0.3, 0.4, 0.5],
    'LEARN': [0.2, 0.3, 0.5, 0.8, 1.0],
    'CLIP': [1.0, 1.5, 2.0, 3.0, 4.0],
    'NEAR_DISLIKE': [0.80, 0.85, 0.90, 0.95, 0.98],
}
SEED = {'verse_id': 26137}  # John 3:16

# Each constant is swept across every (reader, mood) combination below, not just one -- MOOD_MU's own term is
# forced to exactly 0 whenever no mood vector is given (tool/trails.py's trail_next: `... if m is not None else
# np.zeros(...)`), and NEAR_DISLIKE is only ever read for verses in `disliked`, which AlwaysLikeReader never
# produces -- sweeping only one (no-mood, always-like) scenario made both constants mathematically guaranteed to
# show zero effect regardless of their real sensitivity. See this plan's own ledger for the investigation.
READERS = [('always_like', AlwaysLikeReader), ('always_dislike', AlwaysDislikeReader), ('mixed', MixedPatternReader)]

# The exploration cadence (cadence = max(1, floor(8 - 5*focus + 0.5)), tool/trails.py's trail_next) is not a
# named module constant -- its 8 and 5 are literals embedded in the function body, so swept_constant's
# monkeypatching mechanism cannot vary it directly. Its sensitivity is measured indirectly instead, by sweeping
# the existing `focus` parameter play_trail() already accepts (which drives the same formula) -- note `focus`
# also scales the novelty weight (NOVELTY_BASE + NOVELTY_FOCUS * focus), so a difference in this sweep is not
# attributable to cadence alone.
FOCUS_CANDIDATES = [0.1, 0.3, 0.5, 0.7, 0.9]


COMFORT_GENES = None  # filled in lazily from assets/trail_moods.json by _comfort_genes(), avoids a module-load-time file read


def _comfort_genes():
    global COMFORT_GENES
    if COMFORT_GENES is None:
        moods_data = json.loads((ROOT / 'assets' / 'trail_moods.json').read_text('utf-8'))['moods']
        COMFORT_GENES = next(m for m in moods_data if m['id'] == 'comfort')['genes']
    return COMFORT_GENES


MOOD_SCENARIOS = [('no_mood', []), ('comfort', None)]  # the comfort gene list is substituted in _run_one()


def _run_one(trails, reader_cls, moods_key):
    moods = [] if moods_key == 'no_mood' else [_comfort_genes()]
    mv = None if moods_key == 'no_mood' else trails.mood_vector(moods)
    events = []
    run = play_trail(trails, SEED, reader_cls(), moods=moods, k=5, focus=0.5, mood_strength=0.5, steps=20, _events_out=events)
    target = int(trails.dominant[trails.row_of[SEED['verse_id']]])
    picks = [step['hits'][0]['verse_id'] for step in run if step['hits']]
    return {
        'picks': picks,
        'taste_convergence': taste_convergence(run, target_family=target),
        'flow_coherence': flow_coherence(trails, run),
        'exploration_cost': exploration_cost(run),
        'novelty_pairs': len(novelty_spacing(trails, run)),
        'mood_pull': mood_pull(trails, run, mv),
        'no_repeats_ok': no_repeats(run),
        'near_dislike_ok': near_dislike_ok(trails, run, events),
    }


def sweep():
    trails = trails_module.Trails(str(RET))
    baseline = {f'{reader_name}/{mood_name}': _run_one(trails, reader_cls, mood_name)
                for reader_name, reader_cls in READERS for mood_name, _ in MOOD_SCENARIOS}
    report = {'baseline': baseline, 'constants': {}, 'exploration_cadence_via_focus': {'current': 0.5, 'candidates': []}}
    for name, values in CANDIDATES.items():
        current = getattr(trails_module, name)
        rows = []
        for v in values:
            with swept_constant(trails_module, name, v):
                scenario_results = {f'{reader_name}/{mood_name}': _run_one(trails, reader_cls, mood_name)
                                     for reader_name, reader_cls in READERS for mood_name, _ in MOOD_SCENARIOS}
            flagged = any(not r['no_repeats_ok'] or not r['near_dislike_ok'] for r in scenario_results.values())
            rows.append({'value': v, 'is_current': v == current, 'scenarios': scenario_results, 'flagged': flagged})
        report['constants'][name] = {'current': current, 'candidates': rows}
    for focus in FOCUS_CANDIDATES:
        events = []
        run = play_trail(trails, SEED, AlwaysLikeReader(), moods=[], k=5, focus=focus, mood_strength=0.5, steps=20, _events_out=events)
        m = {
            'exploration_cost': exploration_cost(run), 'flow_coherence': flow_coherence(trails, run),
            'no_repeats_ok': no_repeats(run), 'near_dislike_ok': near_dislike_ok(trails, run, events),
        }
        report['exploration_cadence_via_focus']['candidates'].append(
            {'focus': focus, 'is_current': focus == 0.5, **m, 'flagged': not m['no_repeats_ok'] or not m['near_dislike_ok']})
    return report


def _row_is_flat(row, baseline):
    """True if a candidate row's picks are identical to the baseline's for every scenario -- meaning this
    candidate value had no observable effect in any of the scenarios actually run (not just the one that used
    to be the sweep's only scenario)."""
    return all(row['scenarios'][key]['picks'] == baseline[key]['picks'] for key in baseline)


if __name__ == '__main__':
    report = sweep()
    OUT.mkdir(exist_ok=True)
    (OUT / 'trail-tuning-sweep.json').write_text(json.dumps(report, indent=1), 'utf-8')
    print(f'-> {OUT / "trail-tuning-sweep.json"}')
    for name, data in report['constants'].items():
        flat_values = [row['value'] for row in data['candidates'] if _row_is_flat(row, report['baseline'])]
        print(f"\n{name} (current = {data['current']}):")
        for row in data['candidates']:
            flag = ' FLAGGED (breaks no-repeat/near-dislike)' if row['flagged'] else ''
            cur = ' <- current' if row['is_current'] else ''
            differs = [key for key in report['baseline'] if row['scenarios'][key]['picks'] != report['baseline'][key]['picks']]
            changed = f'changed picks in: {", ".join(differs)}' if differs else 'no scenario changed picks'
            mp = row['scenarios']['always_like/comfort']['mood_pull']
            print(f"  {row['value']:>6}  {changed}  mood_pull(always_like/comfort)={mp:+.3f}{cur}{flag}")
        if len(flat_values) == len(data['candidates']):
            print(f"  -- NOTE: every candidate value left every scenario's picks unchanged (across "
                  f"{len(report['baseline'])} reader/mood scenarios, not just one) -- a real finding about this "
                  f"constant's weight relative to the rest of score(), not a sweep blind spot.")
    print(f"\nexploration cadence (via focus, current = 0.5) -- cadence itself is a literal in trail_next's body,"
          f" not a named constant; focus is the nearest sweepable proxy. Note: focus also scales the novelty"
          f" weight (NOVELTY_BASE + NOVELTY_FOCUS*focus), so a difference here is not attributable to cadence alone:")
    for row in report['exploration_cadence_via_focus']['candidates']:
        flag = ' FLAGGED (breaks no-repeat/near-dislike)' if row['flagged'] else ''
        cur = ' <- current' if row['is_current'] else ''
        print(f"  focus={row['focus']:>4}  explore_cost={row['exploration_cost']:.3f}  flow={row['flow_coherence']:.3f}{cur}{flag}")
