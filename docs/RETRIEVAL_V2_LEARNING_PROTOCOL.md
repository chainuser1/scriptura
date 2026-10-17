# Exploratory learning follow-up

Recorded after reviewing the fixed v2 comparisons, before fitting these models.
This is an exploratory follow-up, not a new untouched confirmatory test.

Train only on assistant-reviewed passages for the 24 development intents. The
12 challenge intents, their wordings, and their judgments are excluded from
training and parameter selection. Their prior baseline results are already
known. Freeze the two models below without tuning on challenge performance.

- Four full-corpus-standardized signals: dense, sparse, exact ColBERT, raw genome.
  No book, verse identity, editorial family weights, named categories, volume
  offsets, or behavioral events are model inputs.
- Pairwise logistic regression on unequal grades, symmetric pairs and equal
  total training weight per intent. Fixed C=1, no intercept, maximum 2,000 steps.
- Compare a linear model and degree-two polynomial features with training-only
  standardization. The nonlinear model tests signal interactions; it is not a
  language model or a validated intent gate.
- Rank the entire corpus on the 12 challenge queries. Review all newly surfaced
  top-five passages against corpus text, hiding method and rank. Keep prior
  judgments immutable. Compare complete top-five lists with Compass and the
  unbalanced baseline. Report all models and exploratory paired intervals.
- Save parameters, train/test intent IDs, input hashes, and coverage. Do not
  integrate or certify from assistant judgments. These judgments can advance
  development without pretending to replace actual reader validation.

## Domain amendment before follow-up metrics

Inspection of newly surfaced text found severe full-corpus extrapolation. A
negative dense coefficient and unconstrained polynomial scores can reward
unrelated low-similarity passages outside the training candidate distribution.
Keep both full-corpus failures and additionally evaluate the same fitted models
restricted to the original candidate pool. No refitting, new hyperparameters, or
challenge-label training. This tests candidate-domain restriction separately from
learning. Report it as a post-inspection diagnostic, not a preplanned success.
