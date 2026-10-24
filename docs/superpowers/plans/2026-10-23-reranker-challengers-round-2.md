# Reranker challengers round 2: gte-reranker-modernbert-base + Ettin vs. Apollos (Nemotron) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a trustworthy, blind-graded comparison of gte-reranker-modernbert-base (149M) and two Ettin reranker sizes (150M, 400M) against the already-shipped Apollos (Nemotron) and Ezra (BGE) methods, using this project's own 36-question held-out answer key and the exact evaluation discipline of `docs/ANSWER_FOCUS_NEMOTRON_HELDOUT_PROTOCOL.md` — frozen inputs, blind grading, a pre-registered pass/fail rule. This is a research task: no application code changes, no new default, no decision to replace Apollos. It only produces numbers.

**Architecture:** Reuses the existing offline evaluation pipeline exactly: `tool/answer_focus_wide_pool.py`'s `Corpus`/`Native`/`identity`/`read`/`write` helpers for retrieval and hashing, and `tool/answer_focus_challengers.py`'s `Scorer`-per-model-family / resumable-per-question-JSON / blind-review-packet / fixed-slot-P@5 pattern, extended with two new model families (`gte`, `ettin150`, `ettin400`) scored via `sentence_transformers.CrossEncoder` instead of raw `transformers` (these are plain encoder cross-encoders, not decoder LLMs — no custom prefix/suffix template, no yes/no logit extraction). A lightweight separate smoke task confirms int8 dynamic quantization round-trips correctly for all three new models before the main comparison runs, since "expected to quantize easily" is this plan's one unverified assumption worth checking early and cheaply.

**Tech Stack:** Python (offline tooling only, matches `tool/answer_focus_challengers.py`), `sentence-transformers`, `optimum`/`onnxruntime` for the quantization smoke check, the existing Rust engine's compiled `scripture_engine.dll`/`.so` for Compass retrieval (already present as native code, not touched by this plan).

**Spec:** No separate design doc exists for this work; the spec is `docs/ANSWER_FOCUS_NEMOTRON_HELDOUT_PROTOCOL.md` (the methodology to reuse verbatim) plus the owner's 2026-10-23 request and the research captured in `[memory] lighter-reranker-candidates-research-task.md`.

## Global Constraints

- No application code changes. This plan touches only `tool/`, `docs/`, and `local-benchmarks/` — never `lib/`, `engine/src/`, or anything shipped.
- Frozen question set: reuse the 36-question answer key already established in this research line (`tool/answer_focus_nemotron_heldout_questions.json`, 26 rows: 22 answerable + 4 absent, per that file's own assertions) rather than authoring a new set — the owner has not yet been asked the fresh-vs-reused question from the segment-retrieval design doc's open item, and reusing the already-existing Nemotron held-out set here is a *different*, already-settled question (that set was fresh when authored for Nemotron; reusing it now to compare new challengers against the same frozen baseline is exactly what the challengers protocol already does across rounds).
- Pin every new model's exact HuggingFace revision hash before scoring a single pair, same as `MODELS` does today for Qwen/Nemotron.
- CPU-only host, matching every prior round's stated constraint (`"CPU-only host, four threads, batch size one"`) — no GPU-only numbers get compared to CPU-only baselines without saying so.
- Blind grading only: no method name, rank, or score is visible to whoever grades blind-view.json's passages (same mechanism as `answer_focus_challengers.py`'s `review()`).
- Pre-registered decision rule, written before any score comes in (Task 6), not chosen after seeing results.
- No model selection or shipping decision happens in this plan. The deliverable is `docs/ANSWER_FOCUS_CHALLENGERS_ROUND2_RESULTS.md` reporting numbers plainly, win or lose, matching every prior results doc's own honesty about negative outcomes.

## Review Focus

- **The engine DLL this tooling needs was just deleted tonight** (`engine/target/release/scripture_engine.dll`, removed as part of a disk-cleanup pass in this same session) — a task that assumes it exists and silently gets a confusing `FileNotFoundError` deep in ctypes would waste the first implementer's whole session; Task 1 makes rebuilding it an explicit, checked prerequisite.
- **A `CrossEncoder`-loaded model that silently falls back to a different pooling/head than the one the model card documents** would produce a real but wrong score for every pair — Task 2's smoke test must assert the two-passage sanity check (relevant > irrelevant) the same way `answer_focus_challengers.py` does at line 119, not just that the call doesn't crash.
- **Int8 quantization "working" by not crashing but silently producing garbage scores** (exactly what happened to Apollos's first int8 attempt — the sign-flip bug) — Task 3's quantization smoke check must compare quantized vs. fp32 scores on the same smoke pairs within a numeric tolerance, not just check the export step completes.
- **Resuming a partially-complete run with stale/mismatched candidate data** (a real bug class the existing scripts guard against via `assert data['candidates'] == r['candidates']`) — every new per-model scoring task must carry the same resume-safety assertion, not a weaker version.
- **A reviewer unconsciously inferring which passages belong to which method from passage ordering or formatting quirks**, even with labels hidden — the existing `review()`'s `sorted(items.values(), key=lambda x: hashlib.sha256(...))` shuffle must be reused exactly, not reimplemented slightly differently in a way that reintroduces order-based leakage.

---

## Task 1: Rebuild the native engine (prerequisite, not new code)

**Files:**
- Modify: none (build step only)
- Verify: `engine/target/release/scripture_engine.dll` exists and is loadable

**Interfaces:**
- Consumes: nothing
- Produces: `engine/target/release/scripture_engine.dll`, which every later task's `wide.Native()` call requires

- [ ] **Step 1: Confirm the DLL is missing**

Run: `ls engine/target/release/scripture_engine.dll` (or PowerShell `Test-Path`)
Expected: file not found (it was deleted earlier this session during disk cleanup)

- [ ] **Step 2: Rebuild the engine in release mode**

Run: `cd engine && cargo build --release` (matches how `engine/target/release/scripture_engine.dll` is populated for every other tool script in this repo; no new build config needed)

- [ ] **Step 3: Verify the DLL loads via the existing helper**

Run: `python -I -c "import sys; sys.path.insert(0, 'tool'); from answer_focus_wide_pool import Native; n = Native(); print('ok'); n.close()"`
Expected: prints `ok` with no exception

- [ ] **Step 4: Commit**

Nothing to commit (build artifact, already gitignored like the rest of `engine/target/`).

---

## Task 2: Add gte-reranker-modernbert-base and Ettin scoring to the challengers tool

**Files:**
- Modify: `tool/answer_focus_challengers.py`
- Test: manual smoke run (per step 4 below), matching how the existing `qwen`/`nemotron` smoke check works (no pytest in this tool — it is offline research tooling, consistent with every existing file in `tool/answer_focus_*`)

**Interfaces:**
- Consumes: `wide.Corpus`, `wide.Native`, `wide.read`, `wide.write`, `wide.digest` (all already imported in this file); `source_rows()`, `order(scores)`, `frozen(path, data)` (already defined in this file)
- Produces: `Scorer('gte')`, `Scorer('ettin150')`, `Scorer('ettin400')` — same `.score(query, text) -> dict` interface as the existing `qwen`/`nemotron` entries (`{'score': float, 'tokens_before_truncation': int, 'truncated': bool, 'seconds': float}`), so `run()`/`review()`/`report()` extend to the new names with no further changes beyond the `MODELS` dict and `Scorer.__init__`/`.score` branches

- [ ] **Step 1: Add the three new entries to `MODELS`**

```python
MODELS = {
    'qwen': ('Qwen/Qwen3-Reranker-0.6B', 'e61197ed45024b0ed8a2d74b80b4d909f1255473'),
    'nemotron': ('nvidia/llama-nemotron-rerank-1b-v2', '828765652b05bd439c9789d2a6d093db1caa1443'),
    'gte': ('Alibaba-NLP/gte-reranker-modernbert-base', 'f7481e6055501a30fb19d090657df9ec1f79ab2c'),
    'ettin150': ('cross-encoder/ettin-reranker-150m-v1', '025501c4e0f9bbeb4c5b198318e0089ff061cc14'),
    'ettin400': ('cross-encoder/ettin-reranker-400m-v1', '5dca36282a5d85f368d2544002513a29159b4c9e'),
}
```

These three revision hashes (confirmed via each repo's HF API `sha` field, 2026-10-23) are each repo's current main-branch commit as of this plan's writing — if a repo has moved since, re-verify via `https://huggingface.co/api/models/<repo>` and update this dict before running Task 2, the same input-drift discipline `frozen()` enforces everywhere else in this file.

- [ ] **Step 2: Extend `Scorer.__init__` to load the three new models via `sentence_transformers.CrossEncoder`**

These are plain cross-encoders (unlike Qwen/Nemotron's custom templates/logit extraction) — `sentence_transformers.CrossEncoder(folder, max_length=512)` loads and scores them directly with no custom prefix/suffix. Add a branch: `if name in ('gte', 'ettin150', 'ettin400'):` loads via `CrossEncoder` instead of the existing `AutoModelForCausalLM`/`AutoModelForSequenceClassification` + manual tokenization path, and stores the same `self.identity` shape (`repo`, `revision`, library versions, `dtype`, `device`, `threads`, `batch_size`, `max_length`, `files` digest) for frozen-input consistency with the existing models.

- [ ] **Step 3: Extend `Scorer.score` with a `CrossEncoder`-based branch**

```python
if self.name in ('gte', 'ettin150', 'ettin400'):
    t = time.perf_counter()
    score = float(self.model.predict([(query, text)], convert_to_numpy=True)[0])
    n = len(self.tokenizer.encode(query, text, truncation=True, max_length=512)) if hasattr(self, 'tokenizer') else None
    ...
```
Return the same `{'score', 'tokens_before_truncation', 'truncated', 'seconds'}` shape as the existing branches. If `CrossEncoder` does not expose a separate tokenizer easily for the token-count/truncation fields, it is acceptable to report `tokens_before_truncation: None, truncated: None` for these three models with a one-line comment explaining why — do not fabricate a count.

- [ ] **Step 4: Run each new model's smoke check**

Run: `python -I tool/answer_focus_challengers.py gte` (then `ettin150`, then `ettin400`)
Expected: each prints `"{name} smoke passed; ...s for two pairs"` (reusing the existing `assert smoke[0]['score'] > smoke[1]['score']` check at line 119) before proceeding to score all 2,000 pairs; if the smoke assertion fails, stop and fix the scoring branch before scoring anything else — do not proceed past a failed smoke check, exactly as the docstring at the top of this file already implies for the existing models.

- [ ] **Step 5: Let each model finish scoring all 2,000 pairs (200 candidates × 10 reused test questions)**

Run: same three commands as step 4; they resume automatically via the existing `data['pairs']`-length check, so a second run after an interruption picks up where it left off.
Expected: `"{name}: all 2,000 pairs complete"` for each of the three.

- [ ] **Step 6: Commit**

```bash
git add tool/answer_focus_challengers.py
git commit -m "feat: add gte-reranker-modernbert-base and Ettin reranker scoring to the challengers comparison tool"
```

---

## Task 3: Quantization smoke check for the three new models

**Files:**
- Create: `tool/answer_focus_lighter_quant_smoke.py`
- Test: the script's own assertions (no separate test file — matches this repo's existing pattern of offline tools whose correctness check is their own frozen assertions, e.g. `answer_focus_challengers.py`'s smoke-pair assertion)

**Interfaces:**
- Consumes: the same pinned `(repo, revision)` tuples from Task 2's `MODELS` dict for `gte`, `ettin150`, `ettin400` (import or duplicate the three entries — duplicating is acceptable here since this script's job is independent verification, not reuse of Task 2's `Scorer`)
- Produces: `local-benchmarks/answer-focus-lighter-quant-smoke/<model>.json`, each recording `{fp32_scores: [...], int8_scores: [...], max_abs_diff: float, within_tolerance: bool}` for a small fixed set of smoke pairs

- [ ] **Step 1: Write the script's smoke-pair data and fp32 baseline**

Reuse the exact same two-pair smoke check already used in Task 2/`answer_focus_challengers.py` (`('What is the capital of France?', 'Paris is the capital of France.')` / `('...', 'Water freezes at zero degrees Celsius.')`) plus 1-2 scripture-domain pairs (one real query/relevant-verse pair, one real query/irrelevant-verse pair, pulled from `tool/answer_focus_nemotron_heldout_questions.json`'s existing rows — do not author new scripture pairs for this smoke check). Score all pairs in fp32 via `sentence_transformers.CrossEncoder`, same as Task 2.

- [ ] **Step 2: Export each model to int8 via dynamic quantization and re-score the same pairs**

Use `optimum.onnxruntime`'s `ORTModelForSequenceClassification` + `ORTQuantizer` (the standard path for a `transformers`-compatible sequence-classification cross-encoder; this mirrors the general shape of Ezra's own int8 path, not Apollos's weight-only pivot — dynamic quantization is the thing to try first here, exactly because these are a different, generally quantization-friendlier architecture, and if dynamic quantization produces a sign-flip or garbage-score bug the same way it did for Apollos's first int8 attempt, that is itself the most important finding this task can produce).

- [ ] **Step 3: Assert fp32 and int8 scores agree within tolerance, and write the result file**

```python
max_abs_diff = max(abs(a - b) for a, b in zip(fp32_scores, int8_scores))
within_tolerance = max_abs_diff < 0.05  # same tolerance class as Apollos's own weight-only verification
```
Write `local-benchmarks/answer-focus-lighter-quant-smoke/<model>.json` with the fields listed in Interfaces above, for each of the three models. Do not assert `within_tolerance` is `True` in the script itself — record it and let the report in Task 7 state the finding; a model failing this check is real, useful information, not a bug in the smoke script.

- [ ] **Step 4: Run the script for all three models**

Run: `python -I tool/answer_focus_lighter_quant_smoke.py gte`, then `ettin150`, then `ettin400`
Expected: each writes its result JSON and prints `max_abs_diff` and `within_tolerance` to stdout.

- [ ] **Step 5: Commit**

```bash
git add tool/answer_focus_lighter_quant_smoke.py local-benchmarks/answer-focus-lighter-quant-smoke/
git commit -m "feat: int8 quantization smoke check for gte/Ettin reranker candidates"
```

---

## Task 4: Frozen protocol document

**Files:**
- Create: `docs/ANSWER_FOCUS_CHALLENGERS_ROUND2_PROTOCOL.md`

**Interfaces:**
- Consumes: nothing (this is a document, not code)
- Produces: the frozen protocol Task 5/6/7 implement against — written and committed *before* any scoring runs, matching every prior round's own stated discipline ("Record before challenger inference")

- [ ] **Step 1: Write the protocol document**

Follow `docs/ANSWER_FOCUS_NEMOTRON_HELDOUT_PROTOCOL.md`'s exact structure (Why / Scope / Question set / Procedure / Decision rule). Content specifics for this round:
- **Why:** the owner asked whether a lighter, easier-to-quantize reranker than Apollos (Nemotron) exists; three candidates were identified by web research (not yet validated on this project's own data) — gte-reranker-modernbert-base, Ettin (two sizes), deprioritizing IBM Granite for this first pass since it scored behind gte in IBM's own published comparison.
- **Scope:** compare `compass_top5`, `answer_focus_today_bge10` (Ezra, today's shipped default), `apollos_at200` (today's shipped Apollos/Nemotron, scored the same way `nemotron_at200` was in the original challengers round — this round adds Apollos itself as a baseline method, which the original round did not need to since Apollos didn't exist yet), `gte_at200`, `ettin150_at200`, `ettin400_at200`. Same 512-token limit, same fixed-slot top-5 scoring, same "no generation/fusion/filtering/calibration/selection decision" restriction as every prior round.
- **Question set:** reuse `tool/answer_focus_nemotron_heldout_questions.json`'s 26 questions (22 answerable + 4 absent) rather than authoring a new set — state explicitly that this makes the result exploratory/development data relative to these specific new challengers (they have never been scored against this set before, so it is still meaningfully "unseen" for gte/Ettin/Apollos-as-a-baseline specifically, even though the question set itself has prior history in this research line for other methods).
- **Procedure:** numbered steps mirroring the held-out protocol's, substituting in this round's actual method list and referencing Task 2/3's actual scripts by name.

- [ ] **Step 2: Write the pre-registered decision rule**

Before any score exists, state a concrete bar, e.g.: "gte-reranker-modernbert-base (or whichever Ettin size) is worth further investment only if its direct P@5 is within 0.05 of Apollos's and its any-direct rate does not regress versus Apollos's, on this question set" — adjust the exact numeric margin using the same reasoning as the segment-retrieval design doc's gate (small-N noise floor), but the owner should confirm or adjust this specific number before Task 6 runs (flag it as a one-line decision for the owner in this task's completion message, do not silently pick a number and treat it as final).

- [ ] **Step 3: Commit**

```bash
git add docs/ANSWER_FOCUS_CHALLENGERS_ROUND2_PROTOCOL.md
git commit -m "docs: frozen protocol for round-2 reranker challengers (gte, Ettin) vs. Apollos"
```

---

## Task 5: Score Apollos itself as a baseline method in this comparison

**Files:**
- Modify: `tool/answer_focus_challengers.py` (or a small new script if Apollos's existing scoring code lives elsewhere — check `lib/services/engine/engine_pack.dart`'s `PackKind.apollosInt8` / the Rust `Focus` struct's model-family handling first, per the segment-retrieval design doc's own finding that Apollos's tokenization is a single concatenated string, not a tokenizer pair)

**Interfaces:**
- Consumes: Apollos's actual shipped int8 ONNX pack (`generated-artifacts/.../apollos-int8-weight-only-v1/model.onnx` or wherever `tool/build_engine_pack.py`'s packaging step stages it from — locate this path before writing the step, do not assume it matches Ezra's path pattern)
- Produces: `apollos_at200` scores for the same 10 reused test questions, same `{'score', 'seconds', ...}` shape as the other `_at200` methods, so Task 6's report can include it as a baseline column

- [ ] **Step 1: Locate Apollos's int8 pack files and tokenization format**

Read `engine/src/focus.rs`'s Apollos-specific encode path (referenced in the segment-retrieval design doc as "a single concatenated string... not a tokenizer pair") to confirm the exact input format this scoring script must replicate.

- [ ] **Step 2: Add an `apollos` entry scored via native ONNX Runtime (not `transformers`)**

Apollos already ships as an ONNX pack for the app's own use — score it via `onnxruntime.InferenceSession` directly against the same int8 model file the app ships, rather than re-downloading the original fp32 Nemotron weights from HuggingFace. This is a deliberate, noted difference from how `nemotron_at200` was originally scored in round 1 (round 1 used the fp32/bf16 HuggingFace weights before int8 conversion existed; round 2 can and should score the actual shipped artifact, since that is the real baseline this round is comparing against) — note this difference explicitly in the protocol doc from Task 4 if not already covered there.

- [ ] **Step 3: Run the smoke check and full scoring**

Same two-pair smoke assertion pattern as Task 2, then full 2,000-pair scoring.
Expected: `"apollos: all 2,000 pairs complete"`.

- [ ] **Step 4: Commit**

```bash
git add tool/answer_focus_challengers.py
git commit -m "feat: score the shipped Apollos int8 pack as a baseline method in the round-2 comparison"
```

---

## Task 6: Blind review packet and grading

**Files:**
- Modify: `tool/answer_focus_challengers.py`'s `review()` function (extend the `MODELS`/method-name loop to include `apollos`, `gte`, `ettin150`, `ettin400` — no new function needed if Task 2/5 correctly extended `MODELS`)

**Interfaces:**
- Consumes: all six methods' completed per-question score files from Tasks 2 and 5
- Produces: `local-benchmarks/answer-focus-challengers-round2/blind-view.json` and `review-decisions.json`, same shape as round 1's files, ready for human blind grading

- [ ] **Step 1: Point `OUT` at a new round-2 directory**

Change `OUT = ROOT / 'local-benchmarks/answer-focus-challengers'` to a round-2-specific path (e.g. `local-benchmarks/answer-focus-challengers-round2`) so round 1's results are never overwritten — this is the single most important correctness property of this task: round 1's `test-report.json` must remain readable and unchanged after this round runs.

- [ ] **Step 2: Run `review()` to build the blind packet**

Run: `python -I tool/answer_focus_challengers.py review`
Expected: prints `"N unique passages ready for blind review; no quality scores inferred."` and writes `blind-view.json`/`review-decisions.json` with every `grade: None`.

- [ ] **Step 3: Grade every passage blind**

This step is manual, by the owner or a reviewer with no visibility into which method produced which passage (same discipline as every prior round) — fill in `grade` (0/1/2) and `reason` for every row in `review-decisions.json`. Not automatable; flag to the owner as the one step in this plan that needs their direct time, same as every prior round in this research line required.

- [ ] **Step 4: Commit the completed grading**

```bash
git add local-benchmarks/answer-focus-challengers-round2/review-decisions.json
git commit -m "data: complete blind grading for round-2 reranker challengers comparison"
```

---

## Task 7: Report and decision

**Files:**
- Modify: `tool/answer_focus_challengers.py`'s `report()` function (extend `method_names` to include `apollos_at200`, `gte_at200`, `ettin150_at200`, `ettin400_at200`)
- Create: `docs/ANSWER_FOCUS_CHALLENGERS_ROUND2_RESULTS.md`

**Interfaces:**
- Consumes: Task 6's fully-graded `review-decisions.json`, Task 3's quantization smoke results
- Produces: the final results document — the deliverable this whole plan exists to produce

- [ ] **Step 1: Run the extended report**

Run: `python -I tool/answer_focus_challengers.py report`
Expected: prints direct/related P@5, any-direct rate, and false-promotion counts for all six methods, plus absent-control counts.

- [ ] **Step 2: Write the results document**

Follow `docs/ANSWER_FOCUS_NEMOTRON_HELDOUT_RESULTS.md`'s structure. State plainly, per method, whether Task 4's pre-registered decision rule was met — including the quantization smoke check's `within_tolerance` result for each model from Task 3. If no candidate clears the bar, say so directly (matching this research line's established norm of reporting negative results as real findings, not omissions) and do not recommend proceeding to calibration/shipping. If one does clear the bar, the correct next step is a *new* plan for on-device timing/budget measurement (the same kind of real-phone measurement already done for Apollos on 2026-10-19) — not a decision to ship from this report alone.

- [ ] **Step 3: Update the memory note**

Edit `[memory] lighter-reranker-candidates-research-task.md` to record the actual outcome (not just "not yet evaluated") and link to this round's results doc.

- [ ] **Step 4: Commit**

```bash
git add docs/ANSWER_FOCUS_CHALLENGERS_ROUND2_RESULTS.md tool/answer_focus_challengers.py
git commit -m "docs: round-2 reranker challengers results (gte, Ettin, Apollos baseline)"
```
