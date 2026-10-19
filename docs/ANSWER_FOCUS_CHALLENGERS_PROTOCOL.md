# BGE, Qwen and Nemotron: frozen offline comparison

2026-10-19. Record before challenger inference. No application changes.

Compare Qwen/Qwen3-Reranker-0.6B (revision
`e61197ed45024b0ed8a2d74b80b4d909f1255473`) and
nvidia/llama-nemotron-rerank-1b-v2 (revision
`828765652b05bd439c9789d2a6d093db1caa1443`) against cached native BGE int8.
Sources: https://huggingface.co/Qwen/Qwen3-Reranker-0.6B and
https://huggingface.co/nvidia/llama-nemotron-rerank-1b-v2 .

Reuse the ten previously evaluated calibration-experiment test questions and
their exact 200 Compass candidates (2,000 pairs per model). These questions are
now exploratory development data, not a fresh held-out test. Do not claim a
winner on independent data. Preserve original artifacts and hash all inputs.
Use focal-verse text only, identical across models, without reference labels in
model input. Verify the saved text digest against the corpus before reuse.

Keep official input templates. Qwen uses the published generic web-search
relevance instruction, with no scripture-specific or doctrinal instruction;
score is the final-token yes logit minus no logit. Nemotron uses its official
question/passage template and classification logit, including its bidirectional
attention implementation. Pin and inspect the remote Python implementation.
No generation, preferred-verse rules, learned fusion, filtering or calibration
in this stage. Stable ties preserve Compass order.

CPU-only host, four threads, batch size one, BF16 weights for challengers to limit
memory demand. Cached BGE uses native int8: this is a comparison of these
implementations, with precision and runtime confounds disclosed. Phone readiness
and architecture-only superiority cannot be inferred. Run a two-passage generic
smoke test first. Record runtime, input length, truncations, model file hashes,
library versions and per-query checkpoints. Maximum model input 512 tokens;
retain Qwen's required prefix/suffix. Report truncation rather than pretending
different tokenizers give identical token budgets. If runtime or memory makes a
model impractical here, preserve the failure and report incomplete work.

Review the shuffled union of Compass top five, current Answer Focus top five
(BGE at ten), BGE at 200 top five and each challenger at 200 top five. Hide method,
rank and score from reviewers; bind labels to packet hashes. Grades: 2 direct
answer, 1 related/context-dependent, 0 nonanswer; explicit reasons required.
Do not infer grades from model agreement or treat unjudged passages as negative.
Report fixed-slot direct/related P@5 on eight answerable questions, any-direct
coverage, false promotions, Spanish separately and absent controls separately.
Without a calibrated cutoff all rankers return results on absent controls; raw
score values are not answer probabilities. Full-pool precision is not established
by reviewing top results. A separate probability sample is needed for that.

Complete blinded review before interpreting method quality. Any model selection
requires a new frozen held-out set. Separate per-model calibration, quantization
and physical phone measurements follow only if ranking results justify them.
Qwen 4B is a later desktop/teacher candidate; do not download it in this first
run on this memory- and disk-constrained host. Teacher outputs are fallible
training signals, not truth labels. No doctrinal neutrality claim is made.
