# Retrieval mathematics research for Scriptura

Research date: 2026-10-16. This is a research assessment, not an app change or a
claim that a published result transfers to scripture retrieval. Sources below
are original papers, proceedings, or author publications. The proposed Scriptura
adaptations are explicitly distinguished from published methods.

## What the current system actually leaves unused

The engine takes 200 candidates each from dense, sparse, and weighted-genome
scores, unions those lists, and evaluates ColBERT only on that union
(`engine/src/search.rs:326`). ColBERT therefore cannot introduce a passage that
the other three lanes missed. This is a more concrete opportunity than simply
changing the last weighted sum.

The first experiment found expected anchors somewhere in the current candidate
pool for 83.33% of the 192 proxy queries, but in the final ten for only 46.35%.
Both candidate discovery and ranking need investigation. Anchors are incomplete,
so neither percentage is an estimate of real relevance accuracy.

Earlier local graph diffusion worked only inside an existing candidate set.
Graph expansion into the corpus is a materially different experiment. Likewise,
earlier learned fusion used human verse-to-verse judgments; it did not train or
validate a natural-language intent model.

## Measurements of the existing vectors

Ran `tool/retrieval_geometry_diagnostics.py`, with no relevance labels or pack
modifications. Covariance uses 8,192 sampled unit vectors. Neighbor occupancy
uses 2,048 source verses, ten non-self neighbors each, searched against all
41,995 passages. A uniform-selection control has the same finite sample size.

| Diagnostic | Dense | Weighted genome | Raw genome |
|---|---:|---:|---:|
| Dimensions | 1,024 | 568 | 568 |
| Mean random-pair cosine | 0.425 | 0.383 | 0.402 |
| Entropy effective rank of centered covariance | 241.9 | 175.7 | 171.0 |
| Dimensions carrying 90% of centered variance | 274 | 268 | 270 |
| Share of neighbor slots held by most-selected 1% of passages | 8.59% | 9.39% | 9.27% |
| Maximum appearances of one passage | 10 | 15 | 11 |

The uniform reference's top-one-percent share is 6.51%, not 1%, because the top
1% is selected *after* observing a sparse sample. These results show geometric
concentration and unequal neighbor occupancy, not that central passages are bad.
The corpus is one domain; genome activations are nonnegative. Both help explain
positive average cosine. Whitening is a hypothesis, not an automatic correction.

Across 191 nondegenerate cached query candidate sets, the mean within-query
Pearson correlation between dense and ColBERT scores is 0.889. This is a useful
redundancy diagnostic. It is not error correlation, proof one lane is redundant,
or a probability of correctness. Candidate selection itself affects correlations.

Detailed measurements and file hashes are in
`local-benchmarks/retrieval-research-v2/geometry-diagnostics.json`.

## 1. Independent ColBERT candidate retrieval: highest structural priority

MUVERA builds asymmetric fixed-dimensional encodings whose inner products
approximate multi-vector similarity. It provides a route from stored token
vectors to ordinary maximum-inner-product candidate retrieval. Its approximation
guarantees concern the similarity computation, not relevance or accuracy.
[MUVERA, 2024; revised 2026](https://arxiv.org/abs/2405.19504)

For query tokens Q and passage tokens D, the target is approximately

\[
S(Q,D)=\frac{1}{|Q|}\sum_i\max_j q_i^\top d_j
\approx \phi_Q(Q)^\top\phi_D(D).
\]

Proposed adaptation: derive an additional retrieval index from the existing
ColBERT pack, union its candidates with the current lanes, then use exact MaxSim
to rerank. No new text encoder is inherently required for this experiment.

First establish an offline exact full-corpus MaxSim reference on a small fixed
query set. If its extra candidates add no relevant passages, an approximate
index will not fix that. If they do, compare a simple centroid index with MUVERA.
Measure recall against exact MaxSim and against relevance judgments separately.

Storage matters: 41,995 fixed vectors of 4,096 FP16 dimensions would alone occupy
about 344 MB. This is an arithmetic illustration, not MUVERA's prescribed size.
Dimensions, compression, index overhead, and phone latency must be measured.

PLAID offers another approach using centroid interaction and pruning. Its
published engine is designed around ColBERTv2 representations and indexing;
reusing its principles with BGE-M3 needs an explicit compatibility experiment.
[PLAID, 2022](https://arxiv.org/abs/2205.09707)

## 2. Corpus-graph adaptive retrieval: expand beyond the initial pool

Graph-based Adaptive Reranking (GAR) explores neighbors of highly scored
documents during reranking. It can recover candidates absent from the first
retrieval stage. A 2026 reproduction on reasoning-intensive retrieval also
emphasizes the importance of the reranker's quality.
[GAR, 2022](https://arxiv.org/abs/2208.08942),
[reproduction, 2026](https://arxiv.org/abs/2604.27577)

Proposed Scriptura experiment: precompute separate dense and genome neighbor
graphs. At query time, retrieve normally, score candidates against the original
query, expose graph neighbors, and score those against the same query. Compare
each graph and their union under the same scoring budget. Do not equate an edge
with doctrinal agreement or propagate a neighbor's relevance as certainty.

At 32 neighbors per passage, 32-bit IDs plus 32-bit edge weights cost roughly
10.8 MB per graph before overhead. This makes a bounded traversal worth testing
on-device. A globally connected graph can still amplify hubs or drift into a
nearby theme; exact query scoring is essential.

## 3. Local-density correction: CSLS

CSLS adjusts similarity using neighborhood density. Its original setting is
cross-lingual word translation, so its use here would be an adaptation.
[Conneau et al., 2017/2018](https://arxiv.org/abs/1710.04087)

\[
\operatorname{CSLS}(q,v)=2\cos(q,v)-r_V(q)-r_Q(v).
\]

Here r_V(q) averages similarity to nearby passages; r_Q(v) averages similarity
to nearby queries from a representative query reference set. For one fixed
query, r_V(q) is constant and cannot change its ordering. The passage-side
term supplies the candidate-specific correction.

A passage-only density estimate is feasible immediately but must be labeled a
local-scaling variant, not the original two-domain CSLS. For verse-to-verse
retrieval the source and destination domains can both be passages. Compare this
with current volume balancing and with no correction. It uses local geometry
without identifying books or deciding their desired representation.

Measure relevance as well as neighbor concentration: a correction that merely
suppresses frequently useful passages is not an improvement.

## 4. Shrinkage whitening and low-rank metrics

Whitening has been studied for sentence representations. Its success on those
models does not establish a benefit on an already trained BGE-M3 retriever.
[Whitening sentence representations, 2021](https://arxiv.org/abs/2103.15316)

A regularized geometric experiment is

\[
\tilde x=\operatorname{normalize}\left[(\Sigma+\lambda I)^{-\beta/2}(x-\mu)\right].
\]

Use the same transform for queries and passages in a given space. Compare no
transform, centering only, and partial whitening; full whitening can amplify
noise in small-eigenvalue directions. Preserve the original genome for semantic
labels and explanation. A retrieval coordinate transform does not redefine a gene.

Supervised metric learning instead learns M in

\[
d_M(q,v)^2=(q-v)^\top M(q-v),\qquad M\succeq0.
\]

Classical large-margin metric learning gives an established formulation.
A low-rank factor M=A^T A makes a cheaper derived representation, although the
factorized optimization need not retain the original convexity.
[Weinberger and Saul, 2009](https://jmlr.csail.mit.edu/beta/papers/v10/weinberger09a.html)

This is lower priority than unsupervised transforms: the prior 568-feature
experiment did not show a clear gain, and 60 human-reviewed sources cannot
support an unrestricted matrix. Neither spectral concentration nor PCA variance
retention proves preservation of useful distinctions.

## 5. Optimal transport over ColBERT token vectors

Word Mover's Distance compares documents through transport between word-vector
distributions. Entropic regularization enables Sinkhorn matrix-scaling solvers;
unbalanced transport relaxes the requirement to match all mass on both sides.
[WMD, 2015](https://proceedings.mlr.press/v37/kusnerb15.html),
[Sinkhorn, 2013](https://arxiv.org/abs/1306.0895),
[unbalanced transport](https://arxiv.org/abs/1607.05816)

Proposed adaptation, not a claimed reproduction of WMD: use the existing
contextual ColBERT vectors, with cost C_ij=1-q_i^T d_j. A balanced starting point is

\[
\min_{P\ge0}\langle P,C\rangle+\epsilon\sum_{ij}P_{ij}(\log P_{ij}-1),
\quad P\mathbf1=a,\ P^\top\mathbf1=b.
\]

MaxSim lets every query token independently select its best passage token; many
query tokens may select the same one. Transport coordinates those assignments.
For a short question and a longer verse, partial or unbalanced matching may be
more appropriate than forcing every passage token to participate. But relaxing
mass constraints can also ignore a crucial query term.

Compare on the same top-20 or top-50 candidates before attempting broader use.
Cost is roughly O(T_q T_v d) to form similarities plus O(I T_q T_v) for I scaling
iterations. Test numerical convergence and negation/comparison cases. ColBERT
vectors were trained for MaxSim, so a more sophisticated objective can be worse.

## 6. Retrieval feedback from scripture vectors: ColBERT-PRF

ColBERT-PRF clusters token vectors from initially retrieved passages and adds
discriminative feedback vectors to the query. It can affect reranking and a
second retrieval pass. It does not require an LLM to invent a replacement query.
[Wang et al., 2021](https://arxiv.org/abs/2106.11251)

Proposed experiment: use original-query retrieval as a fixed comparator, expand
with actual scripture token vectors, and measure newly discovered relevant
passages and drift. A reranking-only implementation cannot recover passages
outside its pool; candidate expansion must be tested explicitly.

Feedback selection, cluster count, expansion weights, and stopping conditions
remain statistical choices. A confident first-pass error can reinforce itself.
Do not interpret pseudo-relevance as human confirmation. Start with a single
bounded expansion, no personal behavioral assumptions, and a no-expansion option.

## 7. Correlation-aware fusion and learned gates

Research comparing convex score fusion with reciprocal-rank fusion finds that
simple learned score combinations can be competitive and sample-efficient;
RRF is not a parameter-free guarantee of robustness.
[Bruch et al., 2022/2023](https://arxiv.org/abs/2210.11934)

Proposed gate:

\[
\alpha(q)=(1-\gamma)\alpha_0+\gamma\operatorname{softmax}(W\phi(q)),
\quad s(q,v)=\sum_m\alpha_m(q)\hat s_m(q,v).
\]

The feature vector can contain numeric score-distribution summaries and
cross-lane disagreement. No named query categories are necessary. Gamma is
selected on development data and includes zero, so a constant fusion remains a
candidate. This gate is our proposed adaptation, not a result established by the
cited fusion paper.

For more principled uncertainty weighting, distinguish score covariance from
*relevance-error* covariance. The latter requires judgments; inverting the
observed 0.889 score correlation does not yield justified confidence weights.
Score entropy also depends on arbitrary score scale and temperature.

The engine's earlier peakedness/regex routers already failed to beat a fixed
blend. A new gate must beat strong constant baselines on fresh queries and a
matched compute budget, not just fit these 24 repeatedly studied intents.

## 8. Query adaptation with fixed passage embeddings: CODER

CODER studies contextual document-embedding reranking with retrieved negatives
and listwise training, reusing precomputed document embeddings. Its experiments
support investigating query-side adaptation rather than assuming every passage
must be re-encoded.
[Zerveas et al., EMNLP 2022](https://aclanthology.org/2022.emnlp-main.727/)

Proposed starting point: a small residual query projection q'=normalize(q+Aq),
initialized near identity, with an unchanged passage index. Compare it with
the constant learned fusion and an identity projection. Training needs real
query-to-passage relevance, not just verse similarity. Unjudged candidates are
not automatically negatives. An objective using the full judged list may learn
ordering distinctions absent from the earlier pairwise component experiment.

This is a promising longer-term route to everyday language, but current search
judgments are insufficient to establish it. No inference-time generator is needed.

## 9. Align the dense and genome views with CCA/GCCA

Canonical-correlation methods learn transformations that align multiple views
of the same objects. DGCCA extends this idea to nonlinear transformations and
multiple views; the simpler linear regularized version is the appropriate first
experiment here.
[Benton et al., 2019](https://aclanthology.org/W19-4301/)

Every verse already pairs a dense vector with a genome, so alignment can be
trained from corpus correspondences without relevance labels. Proposed use:
test a shared subspace as one additional retrieval signal, retaining the
original views. Do not force all information into their intersection.

This maximizes cross-view agreement, not user relevance. It can learn common
style or volume information, and query genomes are already predicted from dense
embeddings. Correlated construction and query-versus-passage distribution shift
are reasons to test carefully, not evidence of independent corroboration.

## 10. Spherical geometry for intent and trails

Directional models such as von Mises–Fisher distributions and Riemannian
optimization have been studied for text embeddings.
[Spherical Text Embedding, NeurIPS 2019](https://proceedings.neurips.cc/paper_files/paper/2019/hash/043ab21fc5a1607b381ac3896176dac6-Abstract.html)

A proposed trail model could represent multiple plausible directions:

\[
p(z\mid q,H)=\sum_c\pi_c\,\mathrm{vMF}(z;\mu_c,\kappa_c).
\]

The mixture weights express uncertainty between possible intents; concentrations
express directional spread. A Bayesian update needs a justified observation
likelihood for actual user feedback. A skip cannot be converted into negative
evidence merely by writing a probabilistic formula.

Spherical interpolation uses meaningful trigonometry:

\[
\mathrm{slerp}(a,b;t)=
\frac{\sin((1-t)\theta)}{\sin\theta}a+
\frac{\sin(t\theta)}{\sin\theta}b,
\quad\theta=\arccos(a^\top b).
\]

It defines a path between two directions, not proof that the path matches a
reader's intended journey. Handle coincident and antipodal directions. Sequential
evaluation is still required; this remains a later research track.

## Mathematical changes that do not create better retrieval by themselves

For unit vectors:

\[
\|q-v\|^2=2-2q^\top v,
\qquad\theta(q,v)=\arccos(q^\top v).
\]

Cosine, Euclidean distance, and angle yield the same nearest-neighbor ordering.
A common orthogonal rotation also preserves every dot product. Replacing cosine
with arccos, rotating both spaces together, or appending a monotone score
transform is not a new standalone ranking signal. A nonlinear rescaling can
alter a later fusion, but that is a fusion change requiring evaluation.

Useful geometry changes neighborhoods through learned/estimated metrics,
contextual alignment, or density correction. Useful calculus optimizes a stated
loss or transport objective. Neither mathematical sophistication nor a graph path
establishes entailment, doctrinal correctness, or a user's intent.

Mathematics can eliminate manually specified passage boosts, but it cannot make
the system free of modeling choices. Encoder training, the genome taxonomy,
training judgments, and the objective all influence results. Audit those choices
and measure fidelity to expressed needs; do not describe learned weights as
inherently neutral. A hidden gem should be a newly discovered relevant passage,
not a passage rewarded merely for being unusual.

Hyperbolic methods need evidence that a useful relevance hierarchy exists.
Book/chapter nesting alone does not establish that hierarchy. HNSW/PQ primarily
change search efficiency and approximation; they do not create missing meaning.

## Recent engines: applicability matters more than the headline

XTR changes multi-vector training so useful tokens can be retrieved directly.
WARP makes XTR-style retrieval faster. Neither should be presented as a
drop-in accuracy upgrade for the current BGE-M3 token pack.
[XTR, 2023](https://arxiv.org/abs/2304.01982),
[WARP, 2025](https://arxiv.org/abs/2501.17788)

A May 2026 replication confirms XTR's token-level behavior but does not reproduce
its overall effectiveness advantage over ColBERT in a controlled comparison.
It finds efficiency benefits relevant to IVF-based engines. This supports
testing implementation and training compatibility separately from relevance.
[XTR replication, 2026](https://arxiv.org/abs/2605.00646)

## Next experiments, with the application untouched

| Order | Experiment | What can be reused | Main question |
|---|---|---|---|
| 1 | Full-corpus exact ColBERT oracle, then an independent candidate lane | Existing token pack and query tokens | Are relevant passages excluded before ColBERT sees them? |
| 2 | Corpus-graph candidate expansion under a fixed scoring budget | Dense/genome matrices and existing query scorers | Can query-scored neighbors recover missed passages? |
| 3 | Local-density correction and shrinkage whitening, independently | Existing dense/genome vectors | Do useful neighbors change without editorial volume offsets? |
| 4 | MaxSim vs partial/unbalanced transport on identical candidates | Existing token vectors | Does coordinated matching improve multi-concept relevance? |
| 5 | One-pass vector feedback | Retrieved scripture token vectors | Does expansion recover answers without changing the need? |
| 6 | Learned gate or query projection | Existing vectors plus new query judgments | Does it beat the best fixed/simple model on new intents? |

Test each intervention separately before combinations. For candidate expansion,
report marginal relevance recall, candidate count, and final ranking. For a
reranker, keep candidates fixed. Compare with both volume-balance settings,
Compass, Lantern, and dense-only where applicable. Include cases with the
optional token pack absent. Record cold/warm latency, memory, storage, and scores
on the actual phone; external-paper speedups are not phone measurements.

The existing 192-query set is now a development/proxy set, not a fresh holdout.
Freeze new independent reader intents and judgments before making new quality
claims. Keep translations/paraphrases together, distinguish unjudged discoveries,
report per-language and per-intent failures, and reserve final testing until
selection is complete. Synthetic intent labels or model agreement cannot certify
95–99% accuracy.
