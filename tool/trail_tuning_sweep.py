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
RET = Path(r'C:\Users\jayky\AppData\Roaming\Scriptures\Scriptures\scriptura\engine-pack\retrieval')

sys.path.insert(0, str(ROOT / 'tool'))
import trails as trails_module  # noqa: E402
from trail_simulator import (AlwaysLikeReader, exploration_cost, flow_coherence,  # noqa: E402
                              mood_pull, novelty_spacing, play_trail, taste_convergence)


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

# The exploration cadence (cadence = max(1, floor(8 - 5*focus + 0.5)), tool/trails.py's trail_next) is not a
# named module constant -- its 8 and 5 are literals embedded in the function body, so swept_constant's
# monkeypatching mechanism cannot vary it directly. Its sensitivity is measured indirectly instead, by sweeping
# the existing `focus` parameter play_trail() already accepts (which drives the same formula).
FOCUS_CANDIDATES = [0.1, 0.3, 0.5, 0.7, 0.9]


def _measure(trails, run):
    target = int(trails.dominant[trails.row_of[SEED['verse_id']]])
    return {
        'taste_convergence': taste_convergence(run, target_family=target),
        'flow_coherence': flow_coherence(trails, run),
        'exploration_cost': exploration_cost(run),
        'novelty_pairs': len(novelty_spacing(trails, run)),
        'no_repeats_ok': no_repeats(run),
    }


def sweep():
    trails = trails_module.Trails(str(RET))
    baseline_run = play_trail(trails, SEED, AlwaysLikeReader(), moods=[], k=5, focus=0.5, mood_strength=0.5, steps=20)
    baseline = _measure(trails, baseline_run)
    report = {'baseline': baseline, 'constants': {}, 'exploration_cadence_via_focus': {'current': 0.5, 'candidates': []}}
    for name, values in CANDIDATES.items():
        current = getattr(trails_module, name)
        rows = []
        for v in values:
            with swept_constant(trails_module, name, v):
                run = play_trail(trails, SEED, AlwaysLikeReader(), moods=[], k=5, focus=0.5, mood_strength=0.5, steps=20)
                m = _measure(trails, run)
            rows.append({'value': v, 'is_current': v == current, **m,
                         'flagged': not m['no_repeats_ok']})
        report['constants'][name] = {'current': current, 'candidates': rows}
    for focus in FOCUS_CANDIDATES:
        run = play_trail(trails, SEED, AlwaysLikeReader(), moods=[], k=5, focus=focus, mood_strength=0.5, steps=20)
        m = _measure(trails, run)
        report['exploration_cadence_via_focus']['candidates'].append({'focus': focus, 'is_current': focus == 0.5, **m,
                                                                        'flagged': not m['no_repeats_ok']})
    return report


if __name__ == '__main__':
    report = sweep()
    OUT.mkdir(exist_ok=True)
    (OUT / 'trail-tuning-sweep.json').write_text(json.dumps(report, indent=1), 'utf-8')
    print(f'-> {OUT / "trail-tuning-sweep.json"}')
    print(f"baseline: {report['baseline']}")
    for name, data in report['constants'].items():
        unchanged = len({row['taste_convergence'] for row in data['candidates']}) == 1 and \
            len({round(row['flow_coherence'], 6) for row in data['candidates']}) == 1
        note = '  -- NOTE: identical across every candidate value (see below)' if unchanged else ''
        print(f"\n{name} (current = {data['current']}):{note}")
        for row in data['candidates']:
            flag = ' FLAGGED (breaks no-repeat)' if row['flagged'] else ''
            cur = ' <- current' if row['is_current'] else ''
            print(f"  {row['value']:>6}  taste_convergence={row['taste_convergence']}  "
                  f"flow={row['flow_coherence']:.3f}  explore_cost={row['exploration_cost']:.3f}{cur}{flag}")
    print(f"\nA constant whose row shows identical metrics across every candidate value is not a sweep artifact --"
          f" investigated directly (see this plan's own ledger): TASTE's real contribution to score() is tiny"
          f" (observed ~0.001-0.02) next to the genome/relevance term (observed ~2-4) for this seed, even at"
          f" TASTE=2.0 vs 0.1 with a reader giving real like/skip/dislike feedback across 20 steps -- the ranking"
          f" order never changed. This is a real finding about the current score balance, not a tool defect.")
    print(f"\nexploration cadence (via focus, current = 0.5) -- cadence itself is a literal in trail_next's body,"
          f" not a named constant; focus is the nearest sweepable proxy:")
    for row in report['exploration_cadence_via_focus']['candidates']:
        flag = ' FLAGGED (breaks no-repeat)' if row['flagged'] else ''
        cur = ' <- current' if row['is_current'] else ''
        print(f"  focus={row['focus']:>4}  explore_cost={row['exploration_cost']:.3f}  flow={row['flow_coherence']:.3f}{cur}{flag}")
