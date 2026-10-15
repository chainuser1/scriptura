"""Trails reference (spec docs/superpowers/specs/2026-10-14-trails-design.md, sections 5 and 6).

Pure functions of a request and the installed packs. The Rust port (engine/src/trails.rs) must return the same ordered
verse ids for every golden case; scores agree to 1e-6.
"""
import math
from pathlib import Path

import numpy as np

from similar_verses import SimilarVerses

FAMILY_WEIGHTS = {'B': 0.75, 'I': 0.5, 'N': 0.5, 'Q': 0.0, 'T': 0.75, 'U': 0.75}   # as engine/src/search.rs
REWARD = {'like': 1.0, 'skip': -0.2, 'dislike': -1.0}
LANE_K, WIDE_K = 200, 500
NEAR_DISLIKE = 0.90
LEARN, CLIP, TASTE = 0.5, 2.0, 0.3
DISLIKE_W, SKIP_W = 0.6, 0.2
TOPIC_W = 0.5
NOVELTY_BASE, NOVELTY_FOCUS = 0.1, 0.3
MOOD_MU = 0.6


def zscore(x):
    x = np.asarray(x, dtype=np.float64)
    if len(x) < 2:
        return np.zeros(len(x))
    sd = x.std(ddof=1)
    return np.zeros(len(x)) if sd <= 1e-12 else (x - x.mean()) / sd


def normalise(v):
    n = float(np.linalg.norm(v))
    return v if n <= 1e-12 else v / n


def top_k(scores, ids, rows, k):
    """Rows (indices) of the k best by (-score, verse id)."""
    rows = np.asarray(rows)
    if len(rows) == 0:
        return rows
    order = np.lexsort((ids[rows], -scores[rows]))
    return rows[order][:k]


class Trails:
    def __init__(self, retrieval_dir, topics_db=None):
        sv = SimilarVerses(retrieval_dir)
        self.sv = sv
        self.V = sv.vectors.astype(np.float32)
        self.ids = sv.verse_ids
        self.row_of = sv.row_of
        genes = [l.strip() for l in (Path(retrieval_dir) / 'gene_ids.txt').read_text('utf-8').splitlines() if l.strip()]
        self.genes = genes
        self.gene_index = {g: i for i, g in enumerate(genes)}
        self.family = np.array([ord(g[0]) - ord('A') for g in genes])
        self.sw = np.array([math.sqrt(FAMILY_WEIGHTS.get(g[0], 1.0)) for g in genes], dtype=np.float32)
        v2 = self.V.astype(np.float64) ** 2
        self.E = np.stack([v2[:, self.family == k].sum(axis=1) for k in range(23)], axis=1)
        self.Ebar = self.E.mean(axis=0)
        self.dominant = self.E.argmax(axis=1)
        self.topics = None
        if topics_db and Path(topics_db).exists():
            self.topics = sv._topics(topics_db)

    # ---- seeds, moods, state ----------------------------------------------------------------------------------------
    def seed_vector(self, seed):
        if 'verse_id' in seed:
            return self.V[self.row_of[int(seed['verse_id'])]].astype(np.float64)
        if 'genome' in seed:
            return normalise(np.asarray(seed['genome'], dtype=np.float64))
        if 'verses' in seed:
            rows = [self.row_of[int(v)] for v in seed['verses'] if int(v) in self.row_of]
            return normalise(self.V[rows].astype(np.float64).mean(axis=0))
        raise ValueError('seed needs verse_id, genome or verses (text seeds are encoded by the engine)')

    def mood_vector(self, moods):
        if not moods:
            return None
        m = np.zeros(len(self.genes), dtype=np.float64)
        for mood in moods:
            v = np.zeros(len(self.genes), dtype=np.float64)
            for g in mood:
                v[self.gene_index[g['id']]] = float(g.get('weight', 1.0)) * float(self.sw[self.gene_index[g['id']]])
            m += normalise(v)
        return normalise(m)

    def derive(self, events):
        w = np.zeros(23)
        liked, disliked, skipped, seen = [], [], [], []
        for e in events:
            v, a = int(e['verse_id']), e['action']
            if v not in self.row_of:
                continue
            if v not in seen:
                seen.append(v)
            if a in REWARD:
                w = np.clip(w + LEARN * REWARD[a] * (self.E[self.row_of[v]] - self.Ebar), -CLIP, CLIP)
            {'like': liked, 'dislike': disliked, 'skip': skipped}.get(a, []).append(v)
        return w, liked, disliked, skipped, seen

    # ---- trail_next ------------------------------------------------------------------------------------------------
    def trail_next(self, req):
        k = int(req.get('k', 10))
        focus = float(req.get('focus', 0.5))
        mood_strength = float(req.get('mood_strength', 0.5))
        events = req.get('events', [])
        w, liked, disliked, skipped, seen_events = self.derive(events)
        seed = req['seed']
        g_seed = self.seed_vector(seed)
        extras = [self.seed_vector(x) for x in req.get('extra_seeds', [])]
        V = self.V
        rows = lambda ids: [self.row_of[v] for v in ids if v in self.row_of]  # noqa: E731

        t = g_seed + sum(extras, np.zeros_like(g_seed))
        if liked:
            t = t + V[rows(liked)].astype(np.float64).sum(axis=0)
        if disliked:
            t = t - DISLIKE_W * V[rows(disliked)].astype(np.float64).sum(axis=0)
        if skipped:
            t = t - SKIP_W * V[rows(skipped)].astype(np.float64).sum(axis=0)
        t = normalise(t) if float(np.linalg.norm(t)) > 1e-12 else g_seed
        m = self.mood_vector(req.get('moods') or [])
        tp = normalise(t + 0.5 * mood_strength * m) if m is not None else t

        seen = set(seen_events) | {int(v) for v in req.get('recent', [])}
        if 'verse_id' in seed:
            seen.add(int(seed['verse_id']))
        for x in req.get('extra_seeds', []):
            if 'verse_id' in x:
                seen.add(int(x['verse_id']))
        n = len(self.ids)
        allowed = np.ones(n, dtype=bool)
        for r in rows(seen):
            allowed[r] = False
        if req.get('filter'):
            mask = np.zeros(n, dtype=bool)
            for lo, hi in req['filter']:
                mask |= (self.ids >= lo) & (self.ids <= hi)
            allowed &= mask
        near = np.ones(n, dtype=bool)
        for d in rows(disliked):
            near &= (V @ V[d]).astype(np.float64) < NEAR_DISLIKE

        cos_t = (V @ t.astype(np.float32)).astype(np.float64)
        cos_p = (V @ tp.astype(np.float32)).astype(np.float64)
        overlap = np.zeros(n)
        topic_ok = False
        if self.topics is not None:
            by_verse, postings, _meta = self.topics
            acc = {}
            sources = list(liked) + ([int(seed['verse_id'])] if 'verse_id' in seed else []) + \
                [int(x['verse_id']) for x in req.get('extra_seeds', []) if 'verse_id' in x]
            for v in sources:
                for tp_id, wt in by_verse.get(v, []):
                    acc[tp_id] = acc.get(tp_id, 0.0) + wt
            norm = math.sqrt(sum(x * x for x in acc.values()))
            if norm > 0:
                topic_ok = True
                for tp_id, x in acc.items():
                    for u, wu in postings[tp_id]:
                        r = self.row_of.get(u)
                        if r is not None:
                            overlap[r] += (x / norm) * wu
        has_topic = overlap > 0                    # taken before balancing: balance must not change who is in the topic lane
        vb = float(req.get('volume_balance', 0.0))
        if vb:
            from volume_balance import balance, volume_of_rows
            if getattr(self, '_vol', None) is None:
                self._vol = volume_of_rows(self.ids)
            cos_t, cos_p = (balance(x, self._vol, allowed, vb) for x in (cos_t, cos_p))
            overlap = balance(overlap, self._vol, allowed, vb, positive_only=True)

        widened = 0
        pool_k = LANE_K
        while True:
            ok = allowed & (near if widened == 0 else np.ones(n, dtype=bool))
            elig = np.flatnonzero(ok)
            cg = top_k(cos_p, self.ids, elig, pool_k)
            ct = top_k(overlap, self.ids, elig[has_topic[elig]], pool_k) if topic_ok else np.array([], dtype=int)
            cand = np.unique(np.concatenate([cg, ct]).astype(int))
            if len(cand) >= min(k, len(elig)) or widened >= 2:
                break
            widened += 1
            if widened == 2:
                pool_k = WIDE_K

        if len(cand) == 0:
            return {'mode': 'trail', 'hits': [], 'family_weights': w.tolist(), 'leans': self._leans(w), 'widened': widened,
                    'candidates': 0}

        zg = zscore(cos_t[cand])
        zt = zscore(overlap[cand]) if topic_ok else np.zeros(len(cand))
        taste = TASTE * ((self.E[cand] - self.Ebar) @ w)
        nov_w = NOVELTY_BASE + NOVELTY_FOCUS * focus
        recent_rows = rows([int(v) for v in req.get('recent', [])][-5:])
        if recent_rows:
            sims = (V[cand] @ V[recent_rows].T).astype(np.float64).max(axis=1)
        else:
            sims = np.zeros(len(cand))
        novelty = nov_w * (1.0 - sims)
        mood = MOOD_MU * mood_strength * zscore((V[cand] @ m.astype(np.float32)).astype(np.float64)) if m is not None else np.zeros(len(cand))
        topics_part = TOPIC_W * zt
        score = zg + topics_part + taste + novelty + mood
        order = np.lexsort((self.ids[cand], -score))
        ranked = list(order)

        cadence = max(1, int(math.floor(8 - 5 * focus + 0.5)))
        counts = np.zeros(23)
        for v in seen_events:
            counts[self.dominant[self.row_of[v]]] += 1
        picks, explore_flags = [], []
        taken = set()
        step = int(req.get('step', len(events)))
        for j in range(min(k, len(ranked))):
            choice, explore = None, False
            if (step + j + 1) % cadence == 0:
                remaining = [i for i in ranked if i not in taken]
                fams = sorted({int(self.dominant[cand[i]]) for i in remaining if int(self.dominant[cand[i]]) != 16},
                              key=lambda f: (counts[f], f))
                if fams:
                    want = fams[0]
                    choice = next((i for i in remaining if int(self.dominant[cand[i]]) == want), None)
                    explore = choice is not None
            if choice is None:
                choice = next(i for i in ranked if i not in taken)
            taken.add(choice)
            picks.append(choice)
            explore_flags.append(explore)
            counts[self.dominant[cand[choice]]] += 1

        hits = [{'verse_id': int(self.ids[cand[i]]), 'score': float(score[i]),
                 'parts': {'genome': float(zg[i]), 'topics': float(topics_part[i]), 'taste': float(taste[i]),
                           'novelty': float(novelty[i]), 'mood': float(mood[i]), 'explore': bool(f)}}
                for i, f in zip(picks, explore_flags)]
        return {'mode': 'trail', 'hits': hits, 'family_weights': w.tolist(), 'leans': self._leans(w), 'widened': widened,
                'candidates': int(len(cand))}

    def _leans(self, w):
        order = [int(i) for i in np.argsort(-w, kind='stable')[:2] if w[i] > 0.25]
        return [chr(ord('A') + i) for i in order]

    # ---- explain / taste ------------------------------------------------------------------------------------------
    def explain(self, req):
        a, b = self.V[self.row_of[int(req['a'])]].astype(np.float64), self.V[self.row_of[int(req['b'])]].astype(np.float64)
        c = a * b
        fam_sum = np.array([c[self.family == k].clip(min=0).sum() for k in range(23)])
        total = fam_sum.sum()
        families = []
        if total > 1e-12:
            for k in np.argsort(-fam_sum, kind='stable')[:3]:
                share = fam_sum[k] / total
                if share < 0.05:
                    continue
                idx = np.flatnonzero(self.family == k)
                top = idx[np.argsort(-c[idx], kind='stable')][:3]
                families.append({'family': chr(ord('A') + int(k)), 'share': float(share),
                                 'genes': [{'id': self.genes[i], 'a': float(a[i]), 'b': float(b[i])} for i in top if c[i] > 0]})
        mood_matches = []
        wanted = [g for g in req.get('mood_genes', []) if g in self.gene_index]
        if wanted:
            ranked = sorted(wanted, key=lambda g: (-b[self.gene_index[g]], g))
            mood_matches = [g for g in ranked if b[self.gene_index[g]] > 0][:3]
        return {'mode': 'explain', 'families': families, 'mood_matches': mood_matches, 'shared_terms': [], 'shared_entities': []}

    def taste(self, req):
        score = np.zeros(23)
        for e in req.get('events', []):
            v = int(e['verse_id'])
            if v not in self.row_of or e['action'] not in ('like', 'dislike'):
                continue
            score += (1.0 if e['action'] == 'like' else -1.0) * (self.E[self.row_of[v]] - self.Ebar)
        order = [int(i) for i in np.argsort(-score, kind='stable') if score[i] > 1e-9][:5]
        return {'mode': 'taste', 'families': [{'family': chr(ord('A') + i), 'score': float(score[i])} for i in order]}
