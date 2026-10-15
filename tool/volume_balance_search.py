"""Meaning search check for volume balance (Task 4 of docs/superpowers/plans/2026-10-14-volume-balance.md).

Needs the engine library (engine/target/release, `cargo build --release`): the question encoder lives there.
Rule (fixed before measuring): the share of the top 10 held by the single most frequent volume drops by >= 5 points and
>= 60% of today's top 10 is kept. If the app strength fails, the strength grid is tried for search alone, same rule.

  .venv\\Scripts\\python.exe -I tool/volume_balance_search.py      -> local-benchmarks/volume-balance-search.md
"""
import ctypes
import json
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
from review_sheet import Engine as BaseEngine, load_queries  # noqa: E402
from volume_balance import GRID_STRENGTH, STRENGTH, volume_of_rows  # noqa: E402

N_QUESTIONS = 200
NAMES = ['OT', 'NT', 'BoM', 'D&C', 'PGP']


class Engine(BaseEngine):
    def call(self, body):
        p = self.lib.se_request(self.h, json.dumps(body).encode())
        out = json.loads(ctypes.string_at(p).decode())
        self.lib.se_free_string(p)
        if 'error' in out:
            raise RuntimeError(out['error'])
        return [h['verse_id'] for h in out['hits']]


def main():
    eng = Engine()
    qs = load_queries(N_QUESTIONS, random.Random(11))[:N_QUESTIONS]
    ids = np.arange(1, 41996)
    vol_of = dict(zip(ids.tolist(), volume_of_rows(ids).tolist()))

    def run(strength):
        return [eng.call({'op': 'semantic', 'query': q, 'top_k': 10, 'profile': 'compass', 'volume_balance': strength}) for q in qs]

    def stats(lists):
        dom = np.mean([np.bincount([vol_of[v] for v in l], minlength=5).max() / len(l) for l in lists if l])
        share = np.bincount([vol_of[v] for l in lists for v in l], minlength=5) / sum(len(l) for l in lists)
        return dom, share

    today = run(0.0)
    d0, s0 = stats(today)
    rows = []
    for s in [STRENGTH] + [x for x in GRID_STRENGTH if x != STRENGTH]:
        got = run(s)
        d, sh = stats(got)
        kept = np.mean([len(set(a) & set(b)) / max(len(a), 1) for a, b in zip(today, got)])
        ok = (d0 - d) * 100 >= 5 and kept >= 0.60
        rows.append((s, d, kept, sh, ok))
        print(f'strength {s}: dominant-volume share {100*d:.1f}% (today {100*d0:.1f}%), kept {100*kept:.1f}%  {"PASS" if ok else "fail"}', flush=True)
        if s == STRENGTH and ok:
            break
    win = rows[0] if rows[0][4] else max((r for r in rows if r[4]), key=lambda r: d0 - r[1], default=None)
    L = ['# Volume balance: meaning search (Task 4)', '',
         f'{len(qs)} questions, profile compass, top 10. Rule: dominant-volume share drops >= 5 points, >= 60% of today kept.', '',
         f'Today: dominant-volume share {100*d0:.1f}%; share of all hits ' + ', '.join(f'{n} {100*x:.1f}%' for n, x in zip(NAMES, s0)), '',
         '| strength | dominant-volume share | kept vs today | share of all hits (OT NT BoM D&C PGP) | rule |', '|---|---|---|---|---|']
    for s, d, kept, sh, ok in rows:
        L.append(f'| {s} | {100*d:.1f}% | {100*kept:.1f}% | ' + ' '.join(f'{100*x:.1f}' for x in sh) + f' | {"PASS" if ok else "fail"} |')
    L += ['', f'Search strength: {win[0]}' if win else 'Search strength: none passes; search stays at 0 and the owner is told.']
    out = ROOT / 'local-benchmarks' / 'volume-balance-search.md'
    out.write_text('\n'.join(L) + '\n', 'utf-8')
    print(L[-1], '->', out)


if __name__ == '__main__':
    main()
