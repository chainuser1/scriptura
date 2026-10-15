# Trails: an endless, steerable stream of related verses, with reasons

> Naming: the feature is called a **Trail** (a reader "starts a trail from this verse" and follows it). "Station" was rejected as
> a music word and Pandora's own term.

Status: implemented on branch `trails` (engine port pinned to `tool/trails.py` by goldens; interface reviewed with the owner through audit images). Date: 2026-10-14.

## 1. Purpose

Let a reader pick a verse and read an endless stream of verses related to it, steer the stream with like / skip / dislike, and see
under every verse **why it is in the trail**. The genome project exists to answer "why is this verse tied to that one"; a trail
makes that answer visible while the reader drifts through the canon by theme.

Success looks like: a reader starts a trail from John 3:16, taps like on two verses and dislike on one, and the following verses
visibly follow the likes, avoid the dislike, never repeat, and each carries a short reason that is true (traceable to a real signal).

## 2. Decisions already made

- A trail is a **reading feed**: one verse card at a time. No text to speech (voice quality is not good enough across five languages).
- **Local only.** Trail state lives in the reader's `user.db`; nothing is sent anywhere and there is no central database.
- **Learning is per trail**, on the device. No global model, no usage data, no accounts.
- The learned part is small and readable: **23 family weights** per trail.

## 3. Non-goals

Audio playback; sync between devices (backup and restore already carry `user.db`); sharing trails; ranking by popularity;
recommendations outside the standard works. A model trained across users is **not in v1** (see section 11); v1 contains no
network code for trail data.

## 4. Trail model

A trail has: `id` (uuid), `name` (default: the seed's reference or the question), a seed (a verse, or a typed question), optional
extra seeds, `focus`, up to two `moods`, `mood_strength`, a `volume`, `created_at`, `updated_at`, and an ordered event log.
Events: `shown`, `like`, `skip`, `dislike`, each with `verse_id` and a timestamp. Everything else is derived from the log:

- liked set L, disliked set D, skipped set K, seen set S = seed + every verse ever shown;
- family weights `w` (23 numbers), recomputed by replaying the log (so a restore or a bug fix never leaves stale state).

## 5. Choosing the next verses

Notation: `g_v` is the verse's L2-normalised genome vector (568 genes, the engine's weighted genome matrix); `e_v` is its **family
energy**, the 23-vector `e_v[k] = sum of g_v[i]^2 over genes i of family k` (sums to 1); `ē` is the mean of `e_v` over the canon.
Families are the letters A to W of the gene ids.

**Seed vector.** A verse seed is that verse's `g`. A question seed is the engine's predicted genome of the question. A person or
place seed is the L2-normalised mean of `g` over the entity's linked verses (entities pack). The first seed is `g_seed`; extra seeds
(section 5.1) are summed in with the weight of a like.

**Taste vector.** `t = g_seed + sum(extra seeds) + sum(g_l for l in L) - 0.6 * sum(g_d for d in D) - 0.2 * sum(g_k for k in K)`, then
L2-normalised. When a mood is on, the vector used to fetch the genome neighbours is `normalise(t + 0.5 * mood_strength * m)` so the
pool can reach verses the seed neighbourhood alone would not contain (`m` is defined in 5.2).

**Candidate pool.** The 200 genome neighbours of the taste vector, unioned with the 200 topic-lane neighbours of the seed and the liked
verses (when the topics pack is installed), minus `S`, minus verses whose genome cosine to any disliked verse is 0.90 or higher.

**Topic overlap** of a candidate `u` is its dot product with the L2-normalised sum of the topic vectors (tf-idf, as in the similar-verses lane) of the seed and every liked verse; it is 0 for every candidate when the topics pack is absent.

**Score** (higher is better):

```
relevance = z(genome cosine to t) + 0.5 * z(topic overlap with the seed and liked verses)     # same lanes, same z-score fusion
taste     = 0.3 * dot(w, e_u - ē)                                                              # learned family preference
novelty   = 0.25 * (1 - max cosine of u to the last 5 shown verses)                            # keeps the stream from circling
score(u)  = relevance + taste + novelty
```

Ties break by ascending verse id. Exploration is deterministic: every `n`-th pick takes the best candidate from the family the
trail has shown least, so the stream widens without randomness (reproducible tests). `n` is 6 at the default focus (section 5.1).

**Learning.** After feedback `r` on a shown verse `v` (`like = +1`, `skip = -0.2`, `dislike = -1`):
`w <- clip(w + 0.5 * r * (e_v - ē), -2, 2)`.

**Batches.** The app asks for 10 verses at a time and keeps the queue topped up; feedback invalidates and refills the unplayed queue.

### 5.1 Experience additions (v1)

Taken from what makes a radio-style experience feel alive (responsiveness, visible adaptation, a sense of control):

- **Question seeds.** A trail can start from a typed question ("How do I forgive?"). The seed vector is the engine's predicted
  genome of the question (`g_seed` is replaced by it; `seed_verse` is empty and `seed_text` holds the question). The first batch is
  the nearest verses to that point, so no verse has to be chosen first.
- **Visible adaptation.** The card that follows a like or dislike carries the "Close to the verses you liked / Different from the one
  you disliked" line (reason 5), and the trail header's "This trail leans toward..." line is recomputed after every event.
- **Variety.** "Add variety" adds another seed (a verse, a question, a person, a place) to the trail without resetting its
  history; extra seeds are added to the taste vector with the weight of a like. A **Focus** control (0 to 1) sets how far the
  trail strays: `novelty weight = 0.1 + 0.3 * focus` and the exploration pick happens every `8 - 5 * focus` cards (rounded).
  Default focus 0.5.
- **Never a dead end.** When no candidate passes the filters, widen in order: drop the 0.90 dislike-neighbour exclusion, relax the
  candidate pool to 500, then say the trail has played everything close and offer to add variety.

### 5.2 Moods and volume (v1)

**Moods.** A mood is a small, named set of genes. Choosing up to two moods adds a pull toward that region of the genome. It is a soft
bias, never a filter, and it composes with the seed, likes, dislikes and variety.

- Mood vector `m`: for each gene `i` in the mood, `m_i = weight_i * sw_i` (`sw` is the engine's family weighting of the genome, so
  `m` lives in the same space as the verse vectors; default `weight_i = 1`); all other entries 0; then L2-normalised. Two moods
  add their vectors before normalising.
- Score gains one term: `mood = mu * z(cos(g_u, m))` with `mu = 0.6 * mood_strength` (control 0 to 1, default 0.5).
- Moods are data, not code: `assets/trail_moods.json` (`{id, label, genes[], weights?}`), validated at build time against
  `gene_ids.txt`. Each mood has a plain-language one-line description for the chip tooltip.

The starter set (all gene ids exist in the 568-gene schema; editable by the owner):

| Mood | Genes |
|---|---|
| **Comfort** | `D18_emotion_comfort_consolation`, `D05_emotion_tenderness`, `D08_emotion_peace_stillness`, `D21_emotion_compassion_mercy`, `E08_condition_protection_safety`, `E26_condition_grief_bereavement`, `E28_condition_restoration_healing` |
| **Hope** | `D11_emotion_hope_expectation`, `D26_emotion_relief_deliverance_felt`, `E05_condition_redemption`, `E15_condition_return_reconciliation`, `P06_covenant_blessing_promised` |
| **Courage** | `G24_moral_courage_cowardice`, `D14_emotion_confidence_certainty`, `E20_condition_testing_trial`, `D19_emotion_defiance_resistance`, `E17_condition_vocation_calling` |
| **Gratitude and joy** | `D02_emotion_celebration_joy`, `D16_emotion_gratitude_thanks`, `D10_emotion_wonder_awe`, `E09_condition_provision_need_met` |
| **Repentance** | `D17_emotion_guilt_conviction`, `G32_moral_repentance_turning`, `G14_moral_mercy_over_law`, `E15_condition_return_reconciliation`, `E27_condition_waywardness_straying` |
| **Peace** | `D08_emotion_peace_stillness`, `O01_motion_static_meditative`, `O13_motion_stillness_delayed`, `M08_phenom_rest_physical`, `M15_phenom_silence_absence_sound`, `M12_phenom_lightness_freedom` |
| **Wisdom** | `E21_condition_wisdom_sought`, `T01_pedagogical_mode_didactic`, `R18_doctrinal_density_high`, `T08_application_universal_transferable` |
| **Awe** | `D10_emotion_wonder_awe`, `F14_vision_revelation_dream`, `E25_condition_mystery_unknown`, `D29_emotion_solemnity_gravity` |
| **Warning** | `D12_emotion_warning_caution`, `D03_emotion_urgency`, `G05_moral_consequence_stated`, `D27_emotion_indignation_righteous` |
| **Service** | `G21_moral_stewardship_responsibility`, `G28_moral_solidarity_with_weak`, `G22_moral_hospitality_stranger`, `G25_moral_generosity_stinginess`, `T12_application_missional_outward` |

**Volume.** A hard filter, not a bias: Whole canon (default), Old Testament, New Testament, Bible (both), Book of Mormon, Doctrine
and Covenants, or Pearl of Great Price. The ranges come from the catalog's `volumes` table (`ot` 1 to 23,145; `nt` 23,146 to
31,102; `bom` 31,103 to 37,706; `dc` 37,707 to 41,360; `pgp` 41,361 to 41,995); it uses the engine's existing verse-range filter.

**In the explanation.** When a mood is on and contributes, reason 1 gains: "Matches your mood: Comfort (consolation, tenderness,
protection)", naming at most three of the mood genes the verse is highest in.

## 6. Why this verse

Each card has a "Why this verse" expander with up to five lines, strongest first, each backed by a real signal:

| # | Line | Source |
|---|---|---|
| 1 | Same themes: the top families and, inside them, the two or three genes both verses are high in ("divine love and mercy") | engine `explain`, from the two genome vectors |
| 2 | Shared words and phrases ("whosoever believeth", "only begotten") | engine `explain`, from the sparse index |
| 3 | Shared people or places; "N shared topics" (no topic names) | entities pack; topics pack |
| 4 | A study question both verses answer (curated edges) | answers pack |
| 5 | "Close to the 3 verses you liked" / "Different from the one you disliked" | trail state |

Rules: only lines whose signal is present are shown; the reason is never invented; line 1 states that similarity is a combination of
many features ("one of several shared themes"), since no single gene carries more than a few percent of it.
Gene and family labels come from `assets/genome_labels.json` (project-owned, generated from the gene ids and the family table;
no network, no pack change). Topic names are never shown: the topics pack carries numbers only, by design.

## 7. Interfaces

**Engine** (`engine/src/trails.rs`, exposed through the existing JSON request ABI; Python reference in `tool/trails.py`):

- `trail_next`: `{op, positives, negatives, skips, exclude, family_weights[23], recent[], k, seed_verse | seed_genome[568],
  extra_seeds[], moods: [{genes: [{id, weight}]}], mood_strength, focus, filter?}` returns
  `{hits: [{verse_id, score, parts: {genome, topics, taste, novelty}}], configuration_id}`.
- `explain`: `{op, a, b}` returns `{families: [{family, name, share, genes: [{id, label, a, b}]}], shared_terms: [..], shared_entities: [..]}`.

Both are pure functions of their inputs and the installed packs (no engine-side state), so they are cancellable, deterministic and
testable against the Python reference with golden files, like every other lane.

**Dart** (`lib/features/trails/`): `TrailStore` (SQLite tables below), `TrailController` (queue, feedback, prefetch, replay of
the log into `w`), `TrailsScreen`, `TrailCard`, `WhySheet`, `StarterTrails` (Home), `TasteScreen`, `ReturnBar`. Entry points: "Start a trail" in the verse menu and in search
results; a Trails list in Study.

**Storage** (`user.db`, schema version bump with migration):

```
trails(id TEXT PRIMARY KEY, name TEXT NOT NULL, seed_kind TEXT NOT NULL CHECK(seed_kind IN ('verse','question')),
         seed_verse INTEGER, seed_text TEXT, focus REAL NOT NULL DEFAULT 0.5, moods TEXT NOT NULL DEFAULT '[]',
         mood_strength REAL NOT NULL DEFAULT 0.5, volume TEXT NOT NULL DEFAULT 'all', created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)
trail_seeds(trail_id TEXT NOT NULL, seq INTEGER NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('verse','question','person','place')),
              verse_id INTEGER, text TEXT, entity_id TEXT, PRIMARY KEY(trail_id, seq))
trail_events(trail_id TEXT NOT NULL, seq INTEGER NOT NULL, verse_id INTEGER NOT NULL,
               action TEXT NOT NULL CHECK(action IN ('shown','like','skip','dislike')), at INTEGER NOT NULL,
               PRIMARY KEY(trail_id, seq))
```

Backup export and restore include all three tables; restore merges by `trail_id` and appends events not already present. The verse-layout
check that guards the rest of `user.db` applies to trails too.

## 8. Screen

Above the card: the mood chips (up to two selected), a Volume menu, a Focus slider and a Mood-strength slider behind a "Tune this
trail" button (closed by default so the card stays calm).
One card centred (max 760 px): reference, verse text in the reading face, then **Like**, **Skip**, **Dislike**, and **Why this verse**.
Keyboard: L, S, D, W, Space or Right for skip. A short history strip below; "Open in context" and "Bookmark" reuse the verse tools.
The trail name is editable; a "This trail leans toward…" line names its top two learned families once there are at least three
feedback events. Empty and error states: engine unavailable (explains how search data is installed), no further candidates (says so,
offers to widen by removing dislikes).

### 8.1 Radio-feel rules (v1)

What makes a stream feel alive is mostly restraint. These are requirements, not polish:

- **Feedback is instant and final.** Like, skip and dislike act on tap. No confirmation, no dialog, no "are you sure". Deleting a
  trail uses an Undo snackbar instead of a dialog.
- **No spinner between cards.** The next card is prefetched; if the queue ever runs dry the previous card stays until the next is
  ready (never a blank screen). Budget: next card on screen within 100 ms of a tap.
- **One thing on screen.** One verse, three buttons, Why. Mood, Volume, Focus and Mood strength stay behind "Tune this trail".
- **Motion and touch.** A 180 ms slide to the next card and a light haptic on like and dislike on Android; both switched off by the
  system's reduce-motion and haptics settings.
- **No friction words or counters.** No streaks, scores, limits or interruptions; skipping is always free.
- **Resume exactly.** Reopening a trail shows the card you were on, with the unplayed queue rebuilt from the log.

### 8.2 Starter trails (v1)

About eight ready-made trails on Home so nobody has to choose a seed. Each is data in `assets/trail_starters.json`
(`{id, title, mood, question}`), starts with one tap, and uses a mood plus a question seed:

| Title | Mood | Question seed |
|---|---|---|
| Finding comfort | Comfort | "Where can I find comfort when I grieve?" |
| Hope when it is dark | Hope | "How do I find hope when things look hopeless?" |
| Forgiving and being forgiven | Repentance | "How do I forgive, and how am I forgiven?" |
| Courage to continue | Courage | "Where do I find courage to keep going?" |
| A thankful heart | Gratitude and joy | "What does it mean to be grateful?" |
| Peace in the storm | Peace | "How do I find peace when I am anxious?" |
| Wisdom for a decision | Wisdom | "How do I know what to do?" |
| Serving others | Service | "How can I serve the people around me?" |

The wording is the owner's to edit; the file is validated at build time (mood ids exist, question non-empty).

### 8.3 Your reading taste (v1)

A local screen, derived on the fly from `trail_events` (no new table): the top five families (by summed likes minus dislikes of
`e_v - ē`), the volumes you like from, the moods you use, and a plain sentence ("You lean toward divine love and covenant, mostly in
the Book of Mormon"). A Reset button clears the likes and dislikes that feed it (with an Undo snackbar, per 8.1). It never leaves
the device and is not part of any future upload unless the owner decides otherwise (section 11).

### 8.4 Return bar (v1)

While a trail has at least one event, a thin bar on Home, Read, Search, Study and Settings shows the trail name and the current
verse reference with Resume and a dismiss control. The active trail id is a `user.db` preference (`active_trail`); dismissing clears
it. The bar sits above the bottom navigation on narrow layouts and at the foot of the content area on wide ones, and is hidden on
the Trails screen itself.

## 9. Testing

- Python reference and Rust parity on 12 seeds with scripted feedback (golden lists), including a filter and a verse with no topics.
- Properties: no verse repeats within a trail; a disliked verse's near neighbours (cosine at least 0.90) never appear; with a fixed
  event log the stream is identical on every run; likes move the next batch toward the liked verse's nearest neighbours.
- `explain` returns only signals that are actually present; family shares are non-negative and sum to at most 1.
- Moods: every gene id in `trail_moods.json` exists; with a mood on, the mean cosine of the next 20 verses to the mood vector is
  higher than the same trail without it (property test on 12 seeds x 10 moods); a mood never removes the no-repeat or dislike
  guarantees; volume is a hard filter (no hit outside the chosen volume).
- Human check per mood (the existing sheet pattern): 20 verses from a Comfort trail and 20 from a plain trail, mixed and
  unlabeled, "does this feel like comfort?"; report the rate for every mood before the set is called final.
- Radio feel: no `AlertDialog` appears on like, skip, dislike or trail delete (Undo snackbar only); the previous card stays until the
  next is ready; with reduce-motion on, no transition runs; resume reopens on the same card.
- Starter trails: all eight are present on Home, each starts a trail with the expected mood and question seed; the file's mood ids
  exist. Taste: scripted events produce the expected top families and sentence. Return bar: visible exactly when a trail has events
  and the Trails screen is not showing; dismiss clears it.
- Widget tests: card actions, keyboard, queue refill after feedback, Why sheet, empty states, narrow layout, accessibility guidelines.
- Seeds: a question seed, a person seed and a place seed each produce a first batch whose mean cosine to the seed vector beats the
  canon average; an extra seed changes the next batch without resetting history.
- Speed: one `trail_next` batch of 10 completes in 100 ms or less (median) on the V29 and 50 ms or less on the desktop, so a tap
  never waits.
- Store tests: event replay reproduces `w`; backup and restore round trip; migration from the previous `user.db` version.
- A small human check after build (the existing review-sheet pattern): 20 trails, 10 verses each, "does this belong here?"; report the
  rate. Not a release gate for the code, but it is reported.

## 10. Risks and open points

- **Diffuse similarity:** the genome is 568-dimensional, so a pair's similarity is spread across many genes. The reason line states
  this honestly and aggregates by family; it will sometimes read "several themes" rather than one crisp reason.
- **Vocabulary:** gene labels are derived from ids ("F09 divine love mercy" becomes "Divine love and mercy"); some will read
  awkwardly until the labels file is hand-edited.
- **Coverage of reasons:** shared entities exist for about 15,000 verse links, answers for about 1,000 verses, topics for about half the
  canon, so lines 3 and 4 appear on a minority of cards; line 1 and 2 are always available.
- **Rights:** the topics lane and shared-topic count only operate when the (rights-gated) topics pack is present; the feature
  works without it.
- **Open:** the exploration cadence (every sixth pick at default focus), the mood strength and the other constants in section 5 are
  first values; they should be tuned on the simulator and the human check, not argued in advance.
- **Moods are judgement:** a mood's gene list is a curated opinion about what "comfort" is. It is data in a file, editable, and
  each mood is reported by the human check before it is called final.

## 11. Later: learning from many readers (not in v1)

The intention is to store trail feedback in the cloud eventually and train a better ranker from it. Nothing in v1 depends on
that, but v1 is shaped so that it can be added without a rewrite:

- **The log is already the dataset.** `trail_events` is append-only with a per-trail sequence and a timestamp; each event is a
  `(trail, verse, action)` triple. Replay is how state is rebuilt, so the same log can be uploaded or reduced on a server.
- **The ranker ships as a pack.** A trained ranker would be delivered like the other packs (versioned, hashed, in the bucket index),
  scored by the same human-judged review sheet before it replaces the local rules, and the local per-trail learner remains as the
  fallback and the cold-start.
- **What would be sent, when it exists.** Only trail events: verse ids, actions and coarse time, plus a random install id that is
  not linked to a person. **Owner decision (2026-10-14): notes, highlights, bookmarks, study material, searches and reading position
  are never collected**; only the trail feedback that produces the radio-style effect.
- **Consent is a product change, not a setting.** Reading behaviour on scripture is religious data and sensitive in many
  jurisdictions. It needs a plain opt-in screen (off by default, revocable, with delete-my-data and export), a privacy notice, and a
  review of the target regions' rules before any collection starts.
- **Every promise in the app changes with it.** The Welcome screen ("Nothing personal is ever sent, and no account is needed"), the
  About page and the licences dialog must be rewritten in the same release that adds collection; the update-check statement
  likewise. Until then they stay true.
- **Data minimisation to decide now:** which fields are really needed to train (likely just seed, verse, action, order), the
  retention period, and where the server lives. These belong in a separate spec when the work is scheduled.

## 12. Improvement recommendations (prioritised)

Ordered by value for the reader against cost; the first five are recommended for v1.x, after the core trail ships.

| # | Improvement | Why it helps | Cost |
|---|---|---|---|
| 1 | **Tap a reason to steer.** Each reason chip ("divine love and mercy") can be tapped to say "more of this" (adds that gene or family like a one-off mood) or long-pressed for "less of this". | Turns the explanation into the steering wheel; uniquely genome-native, and the closest thing to Pandora's trait feedback | low: reuses the mood path |
| 2 | **Peek in context.** Expand 2 verses before and after inline, one tap, without leaving the trail. | A verse alone can mislead in scripture; protects the reader from out-of-context reading | low |
| 3 | **Why a dislike.** Long-press dislike offers "off topic", "too familiar", "wrong mood", "not for me today"; each maps to a different update. | Cleaner negative signal than one thumb; better trails and better data later | low |
| 4 | **Today's trail on Home.** Seeded from the verse of the day (or the last read chapter). | Zero-setup entry; the feature is discoverable without anyone looking for it | low |
| 5 | **Five-minute trail with an ending.** An optional end after 10 cards: a summary ("you explored covenant and mercy across 4 books") and one reflection question from the answers pack, then "Continue" or "Open chapter". | Radio never ends; a study session should be able to. Gives a satisfying close and a bridge to the reader | medium |
| 6 | **Export a trail** as Markdown (verses plus reasons) for a study group or journal. Local file, no cloud. | Makes the genome's reasons shareable without a server | low |
| 7 | **Gentle filter.** An option that avoids verses high in wrath, curse and violence genes. | Lets a newcomer or a family reader trust the stream | low |
| 8 | **Smarter cold start.** The first three cards are deliberately spread across the seed's neighbourhood ("which of these speaks to you?"). | Learns the family weights faster, so the third card already feels tuned | low |
| 9 | **Trail simulator.** A script that replays synthetic likers (always likes mercy, always dislikes warning) through the engine to tune the constants in section 5 before the human check. | Replaces argument with measurement; protects the human check from obvious failures | medium |
| 10 | **Localised reasons.** Gene and family labels in the four other languages, reviewed. | The app serves five languages; explanations in English only would feel like a gap | medium, needs translation review |
| 11 | **Skip limits: none.** Do not copy Pandora's skip cap. | There is nothing to monetise and reading should never feel metered | none |

What to avoid: auto-advance on a timer (reading is not listening), a streak or points system, and any ranking by popularity.
