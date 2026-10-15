
## 2026-10-14 - V29 device gate

The engine ran on the vivo V29 (V2250, Android 15). Compass: warm median 195 ms, p95 465 ms, cold first query 700 ms, peak RSS 1,729 MB. Lantern: median 118 ms, p95 128 ms. All E3 gates pass. The first attempts hung at the Welcome screen: files pushed by `adb shell`/`adb push` into a shell-created directory are unreadable by the app (EACCES) until made world-readable; the benchmark tool now chmods them and writes `status.json`/`benchmark.json` to the app files directory.

## 2026-10-14 - automatic first-run data

The folder picker and the manual download panel are gone. On first run the app reads `index.json` from the public bucket, downloads the content zip, the engine zip and the optional word-level index (resumable, SHA-256 checked), unpacks them with the engine library (`se_extract_zip`) and starts search as soon as the engine pack is in. Reading is available as soon as the 24 MB content pack lands. Verified end to end on Windows (`download_e2e_test`, whole flow in a temp profile) and on the V29 from a local test server: 4 GB downloaded, unpacked and installed in about 5 minutes; after install compass median 188 ms, p95 357 ms, RSS 1,771 MB.

## 2026-10-14 - brand pass and ask-first for the 3 GB index

Palette, type and icon grammar follow the owner's brand kit (navy `#0E183E`, one pink accent `#D3167B`, page `#F9FAFB`, ink `#2C2C2C`; Inter for the interface, Source Serif 4 kept for scripture; line icons with exactly one accent). The Scriptures logo is our own: an open book under one lit point (`lib/app/brand.dart` `ScripturesMark`, `tool/make_icon.py`, `assets/icons/scriptures-mark.svg`). Loos (the kit's heading face) is not bundled: its app-embedding licence is unconfirmed; headings use Inter Bold and `Brand`/theme make a swap one line. The word-level index (3 GB) is no longer fetched automatically: Settings and Home offer it with a Not now option; required data (text + search data, about 1 GB) still downloads by itself.

## 2026-10-14 - places, groups and "what this verse speaks to"

Two small packs, both downloaded automatically and both optional for the app to run:

- **entities-pack-v1** (`tool/build_entities_pack.py`): people, places and groups from the legacy AI tags, purified: proper noun only, a verse link survives only when the entity's name occurs in that verse's English text, at least 5 to 8 grounded verses, single-word names must be capitalised, titles/objects dropped, owner-editable `tool/data/entity_overrides.json`. Raw 5,159 entities / 61,700 links become 785 entities / 28,848 grounded links (416 people, 281 places, 88 groups). Topical Guide and Triple Index names are used only to flag corroboration; nothing from them is copied. The linker understands "Who is...", "Where is...", "Tell me about..." in five languages (Python reference, Rust port, golden cases in `test/golden/entity_place_cases.json`).
- **answers-pack-v1** (`tool/build_answers_pack.py`): 9,823 natural study questions (clean translations in four more languages) mapped to 4,283 verses by the question set's own curated edges. The genome-nearest tier is built but off (`--near`): about 7 in 10 neighbours read as relevant, below the bar.
- **Quality**: `tool/quality_audit.py` produces a yes/no sheet and scores it with a Wilson 95% lower bound against 99%. Nothing is certified until a person judges it; the sheet needs about 400 items per section.

## 2026-10-14 - topic overlap as a similarity signal (evaluation, nothing shipped)

`tool/topic_signal_eval.py`: tf-idf cosine over the Topical Guide (TG, 21,991 verses) or Triple Index (TI, 10,717 verses) topic incidence, fused by z-score with the engine's genome-cosine similar-verses profile (G). Two truths with opposite biases. A: verses sharing a study question (biased for G). B: the other index (biased softly for the topic signal). Fusion F at topic weight 0.5, nDCG@10 gain over G with 95% bootstrap interval:

| signal | truth A (question co-targets) | truth B (other index) |
|---|---|---|
| TG | +0.035 [+0.025, +0.047], n=564 | +0.183 [+0.151, +0.215], n=220 |
| TI | +0.023 [+0.014, +0.032], n=580 | +0.218 [+0.199, +0.236], n=574 |

Weight sweep on TG/truth A: 0.25 gives +0.028, 0.5 gives +0.035, 1.0 gives +0.012 (not significant). The signal alone (T) is weaker than G on truth A and stronger on B. Conclusion: a small topic weight helps where topics exist and cannot hurt elsewhere (no topic means F = G). Not built into the engine: the verse-to-topic map is a Church-compiled index (D9 rights), and the proxy truths are not human judgments. Next step if wanted: a human-judged sheet for the fused list, then an optional topics pack.

## 2026-10-14 - topic lane for similar verses

Human judgments by the owner on the 60-source sheet (827 passages): genome only nDCG@8 0.686, genome + topics 0.798, difference +0.112 [+0.042, +0.181]; related-or-better 0.823 -> 0.885. Built: `tool/build_topics_pack.py` (topics-pack-v1: topic numbers and tf-idf weights, no names or text), `similar_with_topics` in the Python reference, `engine/src/topics.rs` plus the fused lane in `similar` (profile `genome_topics_v1`, `"topics": false` for plain genome), golden parity (`test/golden/topics_similar.json`, 20 cases incl. a filter and verses without topics), `PackKind.topics` and automatic install when the host lists it. The shipped lane reproduces the judged result on the same sources (nDCG@8 0.797, 99% of its passages had been judged). Rights: not in the bucket index unless `make_bucket_index.py --include-topics`.

## 2026-10-14 - first quality audit and the second build of the entity and answers packs

The owner's yes/no audit of build 1 (1,100 judgments): entity-verse links 87.5% (people 78%, places 86%, groups 98%), entity identities 88% (descriptions were the main error), question matches from the nearest-neighbour tier 63%. Well short of 99%, so the causes were fixed rather than the claim made:

- machine-written descriptions are no longer shipped; the qualifier is read from the entity id slug ("son of Lehi") or empty;
- links in lists and genealogies are dropped (more than 2 or 3 other names, "begat", "son of");
- a person needs 40 or more tagged verses; same-named rivals are separated by an id-slug cue or by home book (Nephi son of Lehi in 1-2 Nephi), unless one bearer has 3x the rest (Moses);
- a name shared by a person and a place needs a place cue before it (in/to/land of), and a person link is dropped inside "land of X"; months are not places;
- answers: only curated edges with weight 0.3 or more ship (collection-level 0.05-0.2 edges were weakly tied); nearest neighbours stay off.

Result of the same rules on the already-judged sample (survivors only; the rules were designed from its failures, so this is optimistic): links 94% (people 91%, places 91%, groups 98%). Pack sizes after: 106 people, 193 places, 60 groups; 3,948 verses with questions. A fresh audit sheet of the final packs was generated with a new seed (`tool/quality_audit.py --seed 31`: 300 links, all 359 identities, 300 question pairs). Not certified until it is judged.

## 2026-10-14 - second audit and third build

Round 2 audit (owner, 959 judgments) of the second build: entity-verse links 95.3% [92.3, 97.2] (people 92%, places 95%, groups 99%); entities that show a qualifier were judged right 121/124 (97.6%); the 235 entities with no qualifier were all marked "no" because the sheet had nothing to confirm (a sheet-design artefact, not a measured error: link judgments already cover name and type); curated question matches 87% [82.7, 90.3].

Fixes: qualifiers that are a vague single word or repeat the name are dropped ("the king", "Valley", "Kingmen"); a person's name inside "land of / city of X" is never a person link (29 more links); question matches need edge weight >= 0.4 and genome cosine >= 0.88, which scored 98.5% on the judged items (n=65 of 300; thresholds were chosen on that sample, so optimistic). Coverage after: 1,056 verses have questions (down from 3,948). A fresh sample is needed to confirm.

## 2026-10-14 - live bucket verified

`chainuser1/scriptura` serves the final `index.json` (byte-identical to the local one), all five zips at the indexed sizes with Range support (206). `test/integration/live_bucket_test.dart` (SCRIPTURA_LIVE=1) installs everything from the real address into an empty profile on Windows in about 13 minutes (4.05 GB: download, SHA-256 check, unpack, engine start) and answers a meaning search (compass, 20 hits), a reference, a phrase, "Where is Bethlehem?" (place) and "Who is Captain Moroni?" (person). Phone not re-run after the packs changed (not connected at the time).

## 2026-10-14 - phone, fresh install from the final packs

V29, release APK, no side-loaded data; the app fetched the final packs by itself from a local mirror of the bucket over USB (same files and index as the live bucket). Required data (text, search data, entities, answers; about 1 GB) installed in about 3 minutes and search was ready. Without the optional word-level index the Compass default falls back to Lantern: median 119 ms, p95 127 ms, cold first query 113 ms, peak RSS about 1.05 GB, similar verses 8-10 ms. The index was not downloaded on its own (ask-first); a later download seen in the status file was started from the app, not by setup.

## 2026-10-14 - phone with the word-level index from the live bucket; about page; search style

The word-level index (2.9 GB) downloaded on the V29 from the live bucket by the app (started by the owner in-app), unpacked and the engine restarted by itself. Benchmark after: see local-benchmarks/android_benchmark_live_bucket.json. Added: the about page ("The story behind this app", written from the genome project's own records; the author's personal note is a single constant, kAuthorNote, left empty) and Settings > Advanced > Search style (Compass, Wayfarer, Lantern, Chorus, Tide, Feather, Gemini; stored as a preference and sent as the profile of meaning searches).

## 2026-10-14 - text licences recorded

Owner statement: all Bibles in the library are public domain; the LDS triple combination (Book of Mormon, Doctrine and Covenants, Pearl of Great Price) is LDS-licensed text. content.db provenance agrees: English verses 1-31,102 are `kjv`, 31,103-41,995 are `lds`; the other four languages are one source for the whole range. The README, the app's Sources and licences dialog, the About page and the third-party notices now say this, and docs/ARTIFACT_LAYOUT.md flags that `scripture-content-v1.zip` contains LDS-licensed text for verses 31,103-41,995 (permission or licence needed to serve it publicly).

## 2026-10-14 - Trails (branch `trails`)

Shipped: moods, starter trails and plain gene labels (assets); Python reference `tool/trails.py` with property checks and 15 + 3 + 1
goldens; Rust port (`trail_next`, `explain`, `taste` in the engine library, so the engine pack is unchanged and nothing needs
re-uploading); `user.db` schema v2 (trails, seeds, events; v1 files migrate untouched; backup and restore carry trails); Trail page,
Why and Tune sheets, return bar, Study > Trails, Your reading taste; keyboard hints only on desktop and tablets; floating
previous/next chapter buttons in the reader; every page clears the Android status bar.

Decisions: Dislike is worded "Less like this" and is a quiet text action (same weight and key as the plan's Dislike); Home shows four
suggestion chips and a swipeable starter row on phones; the Why panel keeps the card visible on wide windows.

Verification (Windows, this machine): `flutter analyze` clean; `flutter test` 171 passed, 1 skipped; data and reference checks pass;
`cargo test --release` all suites pass including parity with the goldens (ids identical, scores within 1e-5); Windows release,
installer and arm64 APK build. Desktop speed: `trail_next` median 13.5 ms, p90 15.5 ms (budget 50 ms). Phone speed budget (median
100 ms or less) and the by-hand phone check are NOT done: no phone was connected; run `tool/android_device_run.py` and the
checks in the plan (Task 10 steps 3 and 4). Human check of trails (`tool/trail_review_sheet.py`, 10 trails x 12 verses) is
generated at local-benchmarks/trail-review.html and not yet judged: no quality rate is claimed.

Found along the way by the audit images: FilledButton labels had no font family and fell back to the system face (now Inter);
Settings > Line width overflowed a 390 px phone; the Study export button crowded the tabs on phones.

## 2026-10-14 - Looks (reading themes, typefaces, layouts)

Added: nine page colours (Paper, Sepia, Clean, Mist, Forest, Slate, Night, Black, High contrast; contrast 7:1 or better, enforced by
test), two optional open-licence typefaces (Literata, Atkinson Hyperlegible; licence files and notices added), line spacing, verse
numbers (inline / margin / hidden), a cards layout, and a clock-based "dim after dark". Seven looks bundle them (Book, E-reader,
Web, App, Study desk, Night, Large print). Settings > Look and feel shows the looks as live previews (all at once on a wide
window, swipeable on a phone) with the controls under "Fine-tune"; the reader's header has one Aa button that replaces the
size and theme buttons. Trails and the search preview follow the same preferences. Audit images: local-benchmarks/ui-audit/looks-*.png.
Paged (page-turn) reading is not built.

## 2026-10-14 - scope profiles (volume signals muted across the canon, woken inside their volume)

Rule (owner's design): the scope is the set of volumes a filter touches; a gene that tells those volumes apart (eta2 by volume
inside that set >= 0.03) is muted, except protected families (doctrinal R, salvific S, emotional D); inside one volume nothing is
muted and family Q (period and language) is switched on; across the whole canon Q stays off as before. Across the canon 85 genes
are muted, Bible 35. Family Q values come from the unweighted genome (`genome_vectors.f16.npy`) as a 1.8 MB table embedded in the
engine library; no pack changes. Engine: `scope.rs`; request field `scope_profile` ("raw" | "auto") and config key
`scope_profiles` (default false): similar verses and the genome lane of meaning search. Trails are NOT scoped yet. Python
reference `tool/scope_profile.py` and 48 goldens: engine ids equal on all (one near-tie swap within 5e-5 tolerated).
Proxy results (reference, topic lane on): across the canon same-volume 64.2% -> 59.5%, topical agreement 0.280 -> 0.282.
Nothing is user-visible and nothing is adopted: two blind sheets wait for the owner (`local-benchmarks/scope-review-similar.html`,
`scope-review-search.html`); decision rule in `tool/scope_review_sheet.py`.

## 2026-10-15 - scope profiles judged: not adopted

Both blind sheets were judged (60 similar-verse pairs, 40 meaning-search pairs). Rule fixed in advance: adopt a scope only if the
profile wins at least 60% of decided pairs and the lower bound of the 95% Wilson interval is above 50%.

| Sheet / scope | Profile wins | Today wins | Same | Share of decided [95%] |
|---|---|---|---|---|
| Similar verses, across the canon | 12 | 10 | 8 | 55% [35, 73] |
| Similar verses, inside one volume | 8 | 9 | 13 | 47% [26, 69] |
| Meaning search, across the canon | 6 | 7 | 7 | 46% [23, 71] |
| Meaning search, inside one volume | 2 | 4 | 14 | 33% [10, 70] |

No scope passes. The profile changes few lists materially and not reliably for the better, so `scope_profiles` stays false
(engine default), nothing is exposed in the app, and Trails are not scoped. The engine module, the gene table and the reference
stay in the repository, dormant and covered by tests. The topic lane already lowers the volume pull of similar verses (same-volume
72% to 64% in the reference), which is probably why the extra gain is small.

## 2026-10-14 - volume balance replaces scope profiles

The owner's goal stayed the same: across the canon, results must not lean to one volume only because of its style, language or
era. Before building again, four ways were measured on 3,000 random verses (genome lane alone, share of the top 10 from the
source verse's own volume; volume size alone would give 36.8%):

| Way | Same-volume share |
|---|---|
| today | 78.6% |
| a dial per gene, set by its own volume pull | 78.0% |
| every gene's volume offset fully removed | 77.6% |
| the 4 strongest "volume directions" removed | 77.1% (the volume is still 98% guessable from the genome) |
| offset at the output, half strength | 60.2% |

Every gene carries a little of the volume, so no gene or set of genes can be dialled down to fix it. What works is to act where
the volumes compete: for each request and each lane, the engine computes each volume's baseline (the mean of its best scores for
this verse or question) and removes a fraction of it before the candidates are picked. No gene is touched. One volume in scope
changes nothing (the same shift for every row). A volume whose top fraction holds fewer than 5 scores takes the mean offset of
the others, so a small part of a filter is never judged by its own best match. In the topic lanes (where 0 means "no shared
topic") who is in the lane is decided from the raw overlap, rows at 0 stay at 0 and the others never fall below 0. The sparse
word lane (Spark) is not balanced: an offset there would rank verses without the word above verses with it.

Settings were picked by a rule fixed before measuring (bias down at least 8 points, similarity down at most 2%, no volume below
its size share, no volume rising above 1.5x its share), on Similar verses end to end (genome + topic lane, 3,000 sources) and the
first Trails batch (300 seeds): strength 0.75, top fraction 0.03. Results: Similar verses same-volume 75.9% -> 59.5%, average
genome similarity -1.46%; Trails 76.0% -> 61.6%. Meaning search (200 questions, engine): share of the top 10 held by the most
frequent volume 71.2% -> 65.8% (a narrow pass of the 5-point rule), 83.8% of today's top 10 kept. These are the numbers after
the whole-branch review: its three fixes (Spark unbalanced, topic lanes positive-only, the minimum of 5 top scores) changed
the first choice (top fraction 0.005, Similar 54.4%), which no longer passed (Pearl of Great Price flooded), so the grid was
run again under the same rule. Tables: `local-benchmarks/volume-balance-report.md`,
`volume-balance-search.md`.

Engine: `balance.rs` (`Volumes`, embedded `engine/data/volumes.json`), config key `volume_balance` (default 0 = off; the app
passes 0.75), hidden request field `volume_balance` (0..1) for tests and sheets. Applied to similar verses (genome and topic
lanes), meaning search (Echo and Root lanes before the candidate pick; Spark and Thread untouched) and Trails (taste and pool cosines,
topic overlap). Reference: `tool/volume_balance.py`; 80 goldens (`test/golden/volume_balance.json`) match. Trails speed with the
balance on: median 13.8 ms (budget 50). The scope-profile code (gene masks, family Q table, 1.8 MB) is deleted.

Blind sheets (optional for the owner): `local-benchmarks/balance-review-similar.html` (20 across the canon + 20 two-volume
mixes) and `balance-review-search.html` (40 questions). Rule: the feature stays on unless the balanced list wins less than 45%
of the decided pairs (`tool/balance_review_sheet.py --score`).
