"""Volume balance reference (docs/superpowers/plans/2026-10-14-volume-balance.md). The engine port is engine/src/balance.rs.

When two or more volumes are in scope, each volume's baseline for this request (the mean of its best scores) is partly
removed before the volumes compete, so no volume wins only for being itself. One volume in scope = no change.

  .venv\\Scripts\\python.exe -I tool/volume_balance.py --volumes     # write engine/data/volumes.json from catalog.db
  .venv\\Scripts\\python.exe -I tool/volume_balance.py --measure     # grid + decision rule -> local-benchmarks/volume-balance-report.md
"""
import json
import math
import sqlite3
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
VOLUMES = ROOT / 'engine' / 'data' / 'volumes.json'
VOLUME_KEYS = ['ot', 'nt', 'bom', 'dc', 'pgp']
TOP_FRAC = 0.03    # chosen by --measure (Task 1, local-benchmarks/volume-balance-report.md)
MIN_TOP = 5        # a volume's baseline needs at least this many top scores, else it takes the mean offset
STRENGTH = 0.75    # chosen by --measure (Task 1); the app passes it as the engine config key volume_balance


def balance(scores, vol, eligible, strength, top_frac=None, min_top=None, positive_only=False):
    """Subtract strength x each volume's baseline (mean of its best ceil(top_frac * n) eligible scores) when two or more
    volumes have eligible rows. A volume whose top fraction holds fewer than min_top scores takes the mean of the computed
    baselines (so a small part is never judged by its own best match). positive_only (lanes where 0 means "no evidence", like
    topic overlap): rows at 0 stay 0 and the others never fall below 0."""
    top_frac = TOP_FRAC if top_frac is None else top_frac
    min_top = MIN_TOP if min_top is None else min_top
    out = np.asarray(scores, dtype=np.float64).copy()
    present = list(np.unique(vol[eligible]))
    if strength <= 0 or len(present) < 2:
        return out
    base = {}
    for k in present:
        x = out[eligible & (vol == k)]
        n = max(1, math.ceil(top_frac * len(x)))
        if n >= min_top:
            base[k] = float(np.sort(x)[-n:].mean())
    if not base:
        return out
    fill = float(np.mean(list(base.values())))
    raw = out.copy()
    for k in present:
        out[vol == k] -= strength * base.get(k, fill)
    if positive_only:
        out = np.where(raw > 0, np.maximum(out, 0.0), raw)
    return out


def volume_ranges():
    c = sqlite3.connect(f'file:{(ROOT / "generated-artifacts/release/catalog.db").as_posix()}?mode=ro', uri=True)
    got = {k: (a, b) for k, a, b in c.execute('SELECT key, first_verse_id, last_verse_id FROM volumes')}
    return [{'key': k, 'first': got[k][0], 'last': got[k][1]} for k in VOLUME_KEYS]


def volume_of_rows(verse_ids):
    vols = json.loads(VOLUMES.read_text('utf-8'))['volumes']
    out = np.full(len(verse_ids), -1)
    for k, v in enumerate(vols):
        out[(verse_ids >= v['first']) & (verse_ids <= v['last'])] = k
    assert (out >= 0).all(), 'a verse outside every volume'
    return out


# ---- measurement (Task 1 decision rule) -----------------------------------------------------------------------------
GRID_STRENGTH = [0.25, 0.5, 0.75, 1.0]
GRID_FRAC = [0.005, 0.01, 0.03, 0.10]
SIZE_SHARE = None


def _metrics(results, src_rows, vol, vectors):
    """results: list of row lists (top 10) per source row."""
    same = np.array([np.mean([vol[r] == vol[s] for r in rs]) if rs else 0.0 for s, rs in zip(src_rows, results)])
    sim = np.mean([np.mean([float(vectors[s] @ vectors[r]) for r in rs]) for s, rs in zip(src_rows, results) if rs])
    per = [float(same[vol[src_rows] == k].mean()) if (vol[src_rows] == k).any() else float('nan') for k in range(5)]
    hits = np.concatenate([np.asarray(rs, dtype=int) for rs in results if rs])
    share = np.bincount(vol[hits], minlength=5) / len(hits)
    return {'same': float(same.mean()), 'sim': float(sim), 'per': per, 'share': share.tolist()}


def _rule(today, m, size):
    r1 = (today['same'] - m['same']) * 100 >= 8
    r2 = (today['sim'] - m['sim']) / today['sim'] <= 0.02
    r3 = all(p >= s - 1e-9 for p, s in zip(m['per'], size) if not math.isnan(p))
    r4 = all(b <= 1.5 * a + 1e-12 for a, b in zip(today['share'], m['share']))
    return [r1, r2, r3, r4]


def measure(n_similar=3000, n_trails=300):
    sys.path.insert(0, str(ROOT / 'tool'))
    import volume_balance as vbm  # the module the references import (this file may be running as __main__)
    from similar_verses import SimilarVerses, TOPICS_DB
    from trails import Trails
    sv = SimilarVerses()
    ids = sv.verse_ids
    vol = volume_of_rows(ids)
    size = (np.bincount(vol, minlength=5) / len(vol)).tolist()
    rng = np.random.default_rng(7)
    src = rng.choice(len(ids), n_similar, replace=False)
    seeds = src[:n_trails]
    tr = Trails(ROOT / 'generated-artifacts' / 'engine-pack' / 'retrieval', topics_db=TOPICS_DB)

    def run(strength):
        sim = [[sv.row_of[h['verse_id']] for h in sv.similar_with_topics(int(ids[r]), 10, volume_balance=strength)] for r in src]
        trl = []
        for r in seeds:
            out = tr.trail_next({'op': 'trail_next', 'k': 10, 'step': 0, 'seed': {'verse_id': int(ids[r])}, 'extra_seeds': [],
                                 'events': [], 'recent': [], 'moods': [], 'mood_strength': 0.5, 'focus': 0.5,
                                 'filter': None, 'language': 'english', 'volume_balance': strength})
            trl.append([sv.row_of[h['verse_id']] for h in out['hits']])
        return _metrics(sim, src, vol, sv.vectors), _metrics(trl, seeds, vol, sv.vectors)

    today_s, today_t = run(0.0)
    rows = []
    for f in GRID_FRAC:
        vbm.TOP_FRAC = f
        for s in GRID_STRENGTH:
            ms, mt = run(s)
            ok_s, ok_t = _rule(today_s, ms, size), _rule(today_t, mt, size)
            rows.append({'strength': s, 'top_frac': f, 'similar': ms, 'trails': mt, 'rules_similar': ok_s, 'rules_trails': ok_t,
                         'pass': all(ok_s) and all(ok_t)})
            print(f'strength {s} top_frac {f}: similar same {100*ms["same"]:.1f} (today {100*today_s["same"]:.1f}) {ok_s}  '
                  f'trails same {100*mt["same"]:.1f} (today {100*today_t["same"]:.1f}) {ok_t}', flush=True)
    passing = [r for r in rows if r['pass']]
    win = max(passing, key=lambda r: (today_s['same'] - r['similar']['same'], -r['strength'])) if passing else None
    _report(today_s, today_t, rows, win, size)
    return win


def _report(today_s, today_t, rows, win, size):
    names = ['OT', 'NT', 'BoM', 'D&C', 'PGP']
    pct = lambda x: f'{100 * x:.1f}'  # noqa: E731
    L = ['# Volume balance: measurement (Task 1)', '',
         'Rule (fixed before measuring): same-volume share drops >= 8 points; average genome similarity drops <= 2%; every '
         "volume's same-volume share stays >= its size share; no volume's share of all results rises above 1.5x today. "
         'Both Similar verses (3,000 sources) and the first Trails batch (300 seeds) must pass.', '',
         f'Size share: ' + ', '.join(f'{n} {pct(s)}%' for n, s in zip(names, size)), '',
         f'Today: Similar same-volume {pct(today_s["same"])}%, similarity {today_s["sim"]:.4f}; '
         f'Trails same-volume {pct(today_t["same"])}%, similarity {today_t["sim"]:.4f}', '',
         '| strength | top_frac | Similar same-vol | sim change | per volume (OT NT BoM D&C PGP) | Trails same-vol | rules S | rules T | pass |',
         '|---|---|---|---|---|---|---|---|---|']
    for r in rows:
        s, t = r['similar'], r['trails']
        L.append(f'| {r["strength"]} | {r["top_frac"]} | {pct(s["same"])} | {100 * (s["sim"] / today_s["sim"] - 1):+.2f}% | '
                 + ' '.join(pct(p) for p in s['per']) + f' | {pct(t["same"])} | '
                 + ''.join('Y' if x else 'n' for x in r['rules_similar']) + ' | ' + ''.join('Y' if x else 'n' for x in r['rules_trails'])
                 + f' | {"PASS" if r["pass"] else ""} |')
    L += ['', f'Winner: strength {win["strength"]}, top_frac {win["top_frac"]}' if win else 'Winner: none. Nothing passes; report to the owner.']
    out = ROOT / 'local-benchmarks' / 'volume-balance-report.md'
    out.parent.mkdir(exist_ok=True)
    out.write_text('\n'.join(L) + '\n', 'utf-8')
    print('\n'.join(L[-1:]), '->', out)


def main():
    if '--volumes' in sys.argv:
        VOLUMES.write_text(json.dumps({'format': 'volumes-v1', 'volumes': volume_ranges()}, indent=1) + '\n', 'utf-8')
        print('->', VOLUMES)
    if '--measure' in sys.argv:
        measure()


if __name__ == '__main__':
    main()
