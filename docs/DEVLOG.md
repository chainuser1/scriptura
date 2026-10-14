
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
