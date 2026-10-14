"""Similar verses reference (PLAN 6.4, ENGINE_PLAN C4).

Profile `genome_weighted_cosine_v1`: cosine between the stored, family-weighted (sqrt(w) both sides, Q excluded),
L2-normalized verse genomes (`weighted_genome_embeddings.f16.npy`). The source verse is excluded; ties break by
ascending canonical verse ID; an optional allowed set is applied before ranking (a filtered configuration).
This is NOT Experiment D and must not be labeled as such: no query encoding, no dense/sparse/ColBERT signal.

  .venv\\Scripts\\python.exe -I tool/similar_verses.py VERSE_ID [--top-k 10]
"""
import argparse
import sqlite3
import sys
from pathlib import Path

import numpy as np

PROFILE = 'genome_weighted_cosine_v1'
TOPIC_PROFILE = 'genome_topics_v1'
ROOT = Path(__file__).resolve().parent.parent
TOPICS_DB = ROOT / 'generated-artifacts' / 'topics-pack-v1' / 'topics.db'
BUNDLE = ROOT / '.artifact-staging' / 'import-application-v1' / 'extracted' / 'scripture-retrieval-english-v1'


class SimilarVerses:
    def __init__(self, bundle=BUNDLE):
        bundle = Path(bundle)
        self.verse_ids = np.load(bundle / 'verse_ids.npy', allow_pickle=False)
        self.vectors = np.load(bundle / 'weighted_genome_embeddings.f16.npy', allow_pickle=False).astype(np.float32)
        # rows are re-normalised after the f16 round trip, exactly as the native engine does at load
        self.vectors /= np.linalg.norm(self.vectors, axis=1, keepdims=True).clip(1e-12)
        self.row_of = {int(v): i for i, v in enumerate(self.verse_ids)}

    def similar(self, verse_id, top_k=10, allowed_verse_ids=None):
        row = self.row_of.get(int(verse_id))
        if row is None:
            raise KeyError(f'unknown verse id {verse_id}')
        scores = self.vectors @ self.vectors[row]
        mask = np.ones(len(scores), dtype=bool)
        mask[row] = False
        if allowed_verse_ids is not None:
            allowed = np.zeros(len(scores), dtype=bool)
            for v in allowed_verse_ids:
                r = self.row_of.get(int(v))
                if r is not None:
                    allowed[r] = True
            mask &= allowed
        cand = np.flatnonzero(mask)
        order = np.lexsort((self.verse_ids[cand], -scores[cand]))[:top_k]
        return [{'verse_id': int(self.verse_ids[cand[i]]), 'score': float(scores[cand[i]])} for i in order]

    def _topics(self, db):
        if getattr(self, '_topic_db', None) != str(db):
            c = sqlite3.connect(f'file:{Path(db).as_posix()}?mode=ro', uri=True)
            self._topic_meta = dict(c.execute('SELECT key, value FROM meta'))
            by_verse, postings = {}, {}
            for t, v, w in c.execute('SELECT topic, verse_id, w FROM posting'):
                w = float(np.float32(w))
                by_verse.setdefault(v, []).append((t, w))
                postings.setdefault(t, []).append((v, w))
            self._by_verse, self._postings, self._topic_db = by_verse, postings, str(db)
        return self._by_verse, self._postings, self._topic_meta

    def similar_with_topics(self, verse_id, top_k=10, allowed_verse_ids=None, topics_db=TOPICS_DB):
        """Profile genome_topics_v1: genome cosine fused (z-score, ddof=1) with the topic-overlap cosine over the union
        of each lane's top `lane_k` candidates; fused = z(genome) + weight * z(topic); ties by ascending verse id."""
        by_verse, postings, meta = self._topics(topics_db)
        weight, lane_k = float(meta['weight']), int(meta['lane_k'])
        row = self.row_of.get(int(verse_id))
        if row is None:
            raise KeyError(f'unknown verse id {verse_id}')
        g = (self.vectors @ self.vectors[row]).astype(np.float64)
        ok = np.ones(len(g), dtype=bool)
        ok[row] = False
        if allowed_verse_ids is not None:
            allowed = np.zeros(len(g), dtype=bool)
            for v in allowed_verse_ids:
                r = self.row_of.get(int(v))
                if r is not None:
                    allowed[r] = True
            ok &= allowed
        t = np.zeros(len(g), dtype=np.float64)
        for tp, w in by_verse.get(int(verse_id), []):
            for u, wu in postings[tp]:
                r = self.row_of.get(u)
                if r is not None and r != row:
                    t[r] += w * wu
        rows = np.flatnonzero(ok)
        cg = rows[np.lexsort((self.verse_ids[rows], -g[rows]))][:lane_k]
        trows = rows[t[rows] > 0]
        ct = trows[np.lexsort((self.verse_ids[trows], -t[trows]))][:lane_k]
        cand = np.unique(np.concatenate([cg, ct]))

        def z(x):
            if len(x) < 2:
                return np.zeros(len(x))
            sd = x.std(ddof=1)
            return np.zeros(len(x)) if sd <= 1e-12 else (x - x.mean()) / sd

        fused = z(g[cand]) + weight * z(t[cand])
        order = np.lexsort((self.verse_ids[cand], -fused))[:top_k]
        return [{'verse_id': int(self.verse_ids[cand[i]]), 'score': float(fused[i])} for i in order]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('verse_id', type=int)
    ap.add_argument('--top-k', type=int, default=10)
    a = ap.parse_args()
    for r in SimilarVerses().similar(a.verse_id, a.top_k):
        print(r)
    return 0


if __name__ == '__main__':
    sys.exit(main())
