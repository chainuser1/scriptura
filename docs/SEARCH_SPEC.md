# Search behavior specification: filters, empty and degenerate cases

Closes the two remaining Phase 1 items in [PLAN.md](../PLAN.md) section 13 ("Specify filtered search, empty/single-candidate behavior, and tie policy"). Behavior below is implemented in `tool/reference_search.py` (`Searcher.search(..., allowed_verse_ids=...)`) and checked by `test/reference_edge_cases.py`. The native engine must reproduce it; the reference is the oracle.

## 1. Filtered search

A filter is a **new configuration**, not a post-filter on the unfiltered ranking (PLAN 6.2).

1. The engine accepts `allowedVerseIds`: `null` = whole corpus, otherwise a set of canonical verse IDs. The engine does not know books, chapters or canons. The caller resolves "Psalms", "John 3", "New Testament" to verse IDs using the navigation catalog (PLAN 5.2, Phase 4).
2. Unknown IDs (not in the 41,995-verse corpus) are ignored. They are not an error, and they do not change results.
3. The eligible set is applied **before each lane**: dense, sparse and genome each take their top 200 from the eligible rows only. If fewer than 200 rows are eligible, a lane returns all of them.
4. The candidate union, ColBERT scoring and sample z-scores (ddof=1) are computed over that filtered union only. Fused scores from a filtered search are not comparable to unfiltered scores.
5. Allowing every verse is identical to `null`.
6. The cache key and diagnostics must include the filter identity (hash of the sorted allowed-ID set).

## 2. Degenerate inputs

| Situation | Behavior |
| --- | --- |
| Empty query / only whitespace | `invalid_input`. No model work. |
| Query over 512 tokens including specials | `invalid_input` with token count and limit. No truncation. |
| `allowedVerseIds` is an empty set (or has no known IDs) | `status: no_eligible_passages`, zero results, no model work. Not an error. |
| Exactly one candidate | That one passage, fused score `0.0`. |
| Candidate union empty | Zero results. Cannot occur when at least one passage is eligible. |
| A signal is constant over the candidates (std <= 1e-12) | That signal's z-scores are all zero. |
| Non-finite score or vector | `inference_error`. Never rank on NaN or Inf. |
| Fewer than `top_k` candidates | Return all candidates, ranked. |

## 3. Ties and zero scores

- Order by fused score descending, then **ascending canonical verse ID**. The same rule applies inside each lane.
- Sparse zero-score behavior is preserved deliberately: when fewer than 200 passages overlap the query's learned sparse tokens, the remaining sparse slots are filled with zero-score passages in ascending ID order. The validated notebook filled them arbitrarily. This is a known artifact, not a feature. Dropping zero-score sparse candidates would be a different experiment and needs its own evaluation.

## 4. Reproducibility

- Reference environment and golden inputs: `test/golden/experiment_d_reference.json`.
- Packaged-report reproduction (all 20 metric means inside the report's intervals): `test/golden/validation_reproduction_q250.json`.
- Filtered-search results have no packaged reference. Their correctness rests on the invariants above and on the tests, not on matching an external report.
