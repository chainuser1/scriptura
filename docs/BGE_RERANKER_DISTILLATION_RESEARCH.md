# BGE reranking and mobile student distillation: research plan

Date: 2026-10-16

Status: proposed offline research. No reranker experiment, student training, or
mobile validation is reported as completed in this document. Application behavior
and installed model packs are unchanged.

## Objective and constraints

Improve how accurately search addresses a seeker's actual question while retaining
the current BGE-M3 dense, sparse, ColBERT, and genome retrieval foundation. Test
before changing the application. MiniLM is excluded from this proposed work in
accordance with the project owner's preference.

The learning objective is textual relevance and faithful context. It must not
reward preferred theological conclusions, particular verses, popularity, agreement
with the seeker, or emotional comfort or discomfort. A relevant passage can
challenge the premise of a question. Disagreement with a premise is not grounds
for marking a passage irrelevant.

No pretrained model or mathematical objective establishes tradition-free truth.
Pretraining, corpus selection, translations, representations, and supervision all
introduce choices. Make those choices inspectable, preserve uncertainty, and
evaluate fidelity to the text rather than claiming theological neutrality.

## Evidence motivating this experiment

The [completed v2 evaluation](RETRIEVAL_V2_RESULTS.md) found that current Compass
achieved 96.1% related-or-better precision at five, but only 48.3% direct-answer
precision at five on 36 assistant-reviewed questions. These are provisional
evaluation judgments, not independently established reader accuracy.

The existing 1,153 judgments make several failures observable: topical matching
without answering, confused roles and senses, incomplete treatment of multiple
constraints, and missing surrounding context. Mathematical retrieval variants and
learned combinations of four scalar scores did not establish a deployable gain.

All 36 questions have now been inspected. They are development and regression
material, not an untouched final test set. See also the
[mathematical research review](RETRIEVAL_MATHEMATICS_RESEARCH.md) and
[previous learning protocol](RETRIEVAL_V2_LEARNING_PROTOCOL.md).

## Proposed architecture

Offline teacher experiment:

```text
Question
  -> existing BGE-M3 and genome candidate retrieval
  -> candidate verse text or contextual passage text
  -> BAAI/bge-reranker-v2-m3 scores each question-passage pair
  -> reordered evidence for evaluation
```

Conditional mobile experiment:

```text
Offline BGE reranker teacher -> training scores -> compact student

On phone:
Question -> existing retrieval -> compact student -> ranked passages
```

The BGE reranker is a separate cross-encoder, not another name for BGE-M3's
ColBERT scoring. It processes the question and passage together and returns a
relevance score. It does not itself provide a source-span explanation, a verdict
on truth, or a calibrated probability that an answer is correct.

## Stage 1: freeze the experiment and prepare fresh evaluation

Before inference, record the model revision, corpus and pack hashes, query splits,
candidate-selection rules, passage-window construction, truncation, metrics, and
planned comparisons. Freeze development choices before inspecting final test
results. Record amendments rather than silently changing the protocol.

Use existing questions for development. Prepare fresh questions covering negation,
conditions, speaker and addressee, several simultaneous requirements, misleading
premises, context-dependent statements, less obvious relevant passages, and
questions whose answer is absent from the corpus. Include supported languages as
separate evaluation slices; model multilinguality is not proof of language quality.

Keep paraphrases and closely related intents in the same split. For student
training, also track overlapping passages and contexts so performance on familiar
passages can be distinguished from generalization to unseen textual material.

Prepare a relevance rubric before reviewing new outputs. Distinguish direct
address, related or context-dependent material, and nonanswers. Record the source
text and context supporting each judgment. Supporting or challenging a question's
premise is separate from relevance. Ambiguous cases retain their uncertainty.

The assistant can prepare questions and provisional reviews without asking the
owner to choose favored verses. Pool results across methods and hide method names,
scores, and ranks during review. A teacher must not serve as the sole judge of its
own improvement. Assistant-generated or teacher-generated labels do not become
independent ground truth merely by being numerous.

## Stage 2: compare the full BGE reranker offline

Use `BAAI/bge-reranker-v2-m3` as the initial candidate teacher. First demonstrate
that it improves this task; being in the BGE family does not establish superiority.

Compare current Compass with teacher reranking on identical candidate pools. Start
with the current dense, sparse, and genome candidate union; ColBERT continues to
provide the existing late-interaction signal. Report pool size and exclusions.

Compare verse-only input with contextual passage input separately. Define windows
from corpus order and available structural boundaries, avoiding topical selection
or verse-specific exceptions. Freeze window length and truncation on development
data. Preserve the focal verse and deduplicate overlapping windows when scoring
result lists. Evaluate whether the displayed unit actually contains the evidence
responsible for its relevance.

Do not mix a new candidate policy, contextual expansion, and reranking into a
single unexplained improvement. If candidate expansion or a smaller reranking
shortlist is tested, include matched controls and report its effect separately.

Separate retrieval failures from ranking failures: a reranker cannot recover a
relevant passage outside its input pool. Known-positive candidate coverage is a
conditional measurement, not exhaustive corpus recall.

## Stage 3: decide whether the teacher warrants distillation

Primary quality measures are direct-answer precision at five and the fraction of
questions with at least one direct answer in the top five. Also report graded
nDCG at five, related precision, known-positive candidate coverage, and failures by
question type and language. Keep the denominators and evaluation unit explicit.

Use paired, query-group-level uncertainty estimates. Report effect sizes and
individual failures, not just aggregate averages. Treat passage context and
near-duplicate results consistently across methods.

Before the fresh final test, specify the minimum practically useful improvement,
acceptable regression margins, and required sample size using development evidence.
Those numerical thresholds are not yet established by this planning document.
Proceed only when the teacher meets the predeclared criteria. If it fails, retain
the negative result and stop this distillation branch.

The 95-99% ambition requires an operational definition: for example, direct-answer
precision is different from finding one direct answer somewhere in the top five.
Neither a similarity score nor agreement with a teacher measures that ambition.
The current benchmark cannot certify it. Strong reader-facing claims require
independent evaluation of textual fidelity, without asking reviewers to prescribe
favored theological outcomes.

## Stage 4: train and compare compact students only after a teacher gain

First investigate a small interaction model over the existing BGE query and
passage token representations. Test dense, sparse, and genome signals as optional
additional inputs through ablations. Do not assume that additional signals help.
The model would see token-level relationships rather than only four scalar scores.

Teacher scores provide soft ranking supervision on training questions and their
candidate passages. One candidate objective is distribution matching:

```text
p_teacher(d | q) = softmax(teacher_score(q, d) / temperature)
p_student(d | q) = softmax(student_score(q, d) / temperature)
loss = mean over training questions of KL(p_teacher || p_student)
```

These distributions are normalized over a candidate set; they are not probabilities
of scriptural truth or answer correctness. Choose temperature and other training
settings using development data only. Pairwise ranking is an alternative to
compare, not an additional unvalidated requirement. Teacher scores are imperfect
targets and must be checked against the separate relevance evaluation.

Training examples should include natural hard negatives and carefully validated
role, negation, and condition contrasts. Relevant passages challenging a premise
must not be turned into negatives. Synthetic contrasts that change a question's
meaning must be labeled as changed intent, not treated as paraphrases.

Verse IDs, book identities, preferred-verse lists, manually assigned doctrinal
boosts, and inferred agreement from skips are excluded as learned ranking features.
Existing candidate-selection choices remain documented influences on the pipeline;
excluding identity features does not make learned models bias-free.

Token interaction is a hypothesis, not an established solution. Stored ColBERT
representations may have discarded information needed by the full teacher.
Contextual windows may require separate offline encoding and storage. Measure
these costs and representation limits explicitly.

If this student cannot retain useful teacher gains, investigate a compressed
BGE-derived text cross-encoder. Its multilingual vocabulary, embeddings, runtime,
and activations all count toward device cost. A ready-made, sufficiently small
BGE-derived student has not been selected or validated. Avoid promising a model
size based only on removing transformer layers.

## Stage 5: validate mobile feasibility and uncertainty

Compare current search, the full teacher reference, the unquantized student, and
the quantized student. Keep teacher training and inference off the production
phone path. Do not replace or regenerate the production embedding packs during
the research stages.

Measure added download and storage, peak working memory alongside the existing
engine, cold and warm latency, battery use, and sustained thermal behavior on
representative Android and iPhone devices. Test candidate-count and context-length
tradeoffs using development data. Confirm exported model parity and runtime
operator compatibility. Desktop timings do not establish mobile performance.

Freeze device budgets before final device acceptance; this document does not
invent performance limits without representative measurements. Both quality and
device criteria must pass before application integration is proposed.

Evaluate unsupported questions separately. Teacher or student ranking scores are
not calibrated confidence, even after a sigmoid. Any abstention mechanism requires
its own calibration data and held-out evaluation of error versus answer coverage.
Do not hide failures by reporting precision only on the questions that remain.

## Stage 6: evaluate Trails independently

A search gain does not establish a Trails gain. Evaluate whether sequences remain
relevant to the seeker's expressed question, preserve context, avoid repetition,
and respond appropriately when the expressed intent changes.

Current skip penalties and fixed exploration choices are documented unresolved
issues in the v2 report. A skip does not establish disagreement or rejection.
Do not fabricate reader behavior or train theological preferences from assumed
reactions. Research alternatives separately before changing Trails behavior.

## Deliverables and decision sequence

1. Frozen experiment protocol, input identities, and fresh evaluation split.
2. Full BGE reranker comparison with verse/context and candidate controls.
3. Error analysis and an explicit proceed-or-stop decision on distillation.
4. Conditional student experiments, model provenance, and retained-quality results.
5. Conditional device report and separately evaluated uncertainty behavior.
6. Integration proposal only after relevance and device acceptance; separate
   evidence is required for Trails changes.

Keep research scripts, checkpoints, and judgments outside runtime application
inputs. Preserve negative results and disclose reused test material. This plan
records proposed work; it is not evidence that these stages have passed.

## Primary references

- [BAAI BGE-M3 model documentation](https://huggingface.co/BAAI/bge-m3): dense,
  sparse, and multi-vector retrieval; self-knowledge distillation; recommendation
  to combine hybrid retrieval and reranking.
- [BAAI bge-reranker-v2-m3 documentation](https://huggingface.co/BAAI/bge-reranker-v2-m3):
  query-passage cross-encoder scoring and model usage.
- [Distillation versus Contrastive Learning: How to Train Your Rerankers](https://arxiv.org/abs/2507.08336):
  evidence for distillation from a stronger teacher in the paper's tested settings.
  Its student sizes and benchmarks do not establish this compact student's
  feasibility or scripture-search quality.
- [ONNX Runtime mobile deployment](https://onnxruntime.ai/docs/tutorials/mobile/):
  mobile runtime options, quantization, and device performance measurement.
