# Legacy plan — superseded on 2026-10-11

Historical reference only. Do not implement this plan or rely on its status/performance claims. The active plan is [../../PLAN.md](../../PLAN.md). The original content follows unchanged.

# Scriptures Reader Mobile - Implementation Plan

**⚠️ CRITICAL: All code changes MUST be logged in `DEVLOG.md` immediately after implementation.**

Each DEVLOG entry must include:
1. Files modified with line numbers
2. Reference to the PLAN.md section being implemented
3. Explanation of how the change fulfills the plan requirements
4. Any constraints, trade-offs, or important implementation notes

This ensures full traceability from PLAN.md → code → verified benchmarks.

---

Mobile-first Flutter application for offline scripture reading with full search intelligence parity against the web backend.

## Executive Summary

**Goal**: Ship a mobile app that delivers superior search quality to the web backend through mathematically optimized implementations, offline-first with Material Design UI.

**Constraint**: Zero intelligence compromises. Every mathematical operation from `backend/index.js` must be ported exactly, then enhanced through algorithmic improvements.

**Success Metric**: All backend benchmarks pass identically on mobile, with faster response times and improved numerical stability.

---

## Architecture: Full Intelligence Parity

```
lib/
├── search_intelligence/     # Mathematically identical to backend/index.js
│   ├── core/
│   │   ├── constants.dart       # TOTAL_DOCS=41995, EMBED_DIM=768, etc.
│   │   ├── normalization/       # KJV spellings, refs, abbreviations
│   │   ├── fts/                 # FTS5 phrase search, NEAR queries
│   │   ├── semantic/            # Embeddings, HNSW, cosine similarity
│   │   ├── graph/               # PPR, RWR, spectral, clusters
│   │   ├── scoring/             # Specificity, relevance probability
│   │   ├── fusion/              # RRF, MMR rerank
│   │   ├── expansion/           # PMI, concept expansion
│   │   └── optimizer/           # Adam weights, calibration curves
│   ├── pipeline/
│   │   └── run_search_pipeline.dart  # 8-step pipeline orchestration
│   └── models/
│       └── search_result.dart   # Result schema with all fields
├── database/
│   ├── adapters/
│   ├── loaders/
│   └── cache/
├── reader_mode/
│   ├── screens/
│   ├── widgets/
│   └── providers/
└── performance/
    ├── lru_cache.dart
    └── lazy_loader.dart
```

---

## Phase 1: Project Scaffold & Resources (Day 1)

### 1.1 Project Bootstrap

```bash
flutter create scriptures_reader_mobile
cd scriptures_reader_mobile
flutter pub add sqflite path_provider flutter_riverpod go_router freezed_annotation
flutter pub add --dev flutter_test build_runner freezed json_serializable
```

### 1.2 Resource Copy Strategy (EXCLUDE waray)

**Copy to assets/**:
- `lds-scriptures-sqlite.db` (41,995 verses)
- `verse-embeddings.db` (768D raw embeddings)
- `verse-graph.db` (kNN, spectral, PPR, RWR)
- `verse-tags.db` (entities, doctrine tags)
- `topical-guide.db` (3,512 topics)
- `chapter-summaries-fts.db`
- `verse-summaries.db`
- `concept-embeddings.db`
- `footnotes-lds-summaries.db`
- `ylt-scriptures-sqlite.db`
- `rotherham-scriptures-sqlite.db`
- `tagalog-scriptures-sqlite.db`
- `cebuano-scriptures-sqlite.db`
- `spanish-scriptures-sqlite.db`
- `greek-scriptures-sqlite.db`
- `ilocano-scriptures-sqlite.db`
- `japanese-scriptures-sqlite.db`
- `nrsvue-scriptures-sqlite.db`

**ONNX Model**:
- `resources/models/scripture-bge/onnx/model_quantized.onnx`
- Test `onnxruntime_flutter` compatibility

### 1.3 Database Strategy

```dart
// Open read-only from app documents on first launch
Future<void> initializeDatabases() async {
  final docs = await getApplicationDocumentsDirectory();
  for (final db in bundledDatabases) {
    final file = File('${docs.path}/$db');
    if (!file.existsSync()) {
      final data = await rootBundle.load('assets/resources/db/$db');
      await file.writeAsBytes(data.buffer.asUint8List());
    }
  }
}
```

---

## Phase 2: Search Intelligence Port (Days 2-14)

### 2.1 Core Normalization (backend/index.js lines referenced)

**KJV Spellings** (`normalization/kjv_spellings.dart`)
- 18 regex replacements from `shared/data/kjv-spellings.json`
- Applied before query parsing

**Scripture Reference Parser** (`normalization/reference_parser.dart`)
- `parseScriptureReference()` - lines 51-75 in scripture-engine.js
- Handles "book chapter verse", "book chapter:verse" formats
- Book abbreviation expansion

**Query Tokenization** (`normalization/tokenizer.dart`)
- `normalizeSearchText()` - line 2788
- Lowercase, keep alphanumeric + dash only

### 2.2 FTS5 Layer (scripture-engine.js lines referenced)

**Phrase Search** (`fts/phrase_search.dart`)
- `buildFTSPhraseQuery()` - lines 78-81
- `buildFTSTermQuery()` - lines 83-99
- `buildFTSNearQuery()` - lines 101-122
- `buildContentTermQuery()` - lines 171-199
- FTS5 queries return with `_bm25_rank`

**Direct Query Matching**
- `normalizedTextIncludes()` - line 2789
- `_directQueryMatch` flag for exact phrase matches

### 2.3 Semantic Search (`semantic/embeddings.dart`)

**HNSW Index** (`semantic/hnsw.dart`)
- Port `HNSWIndex` class - lines 2343-2467
- M=16, ef=200, serialized format
- `query()` returns top-200 candidates by default

**Embedding Cache** (`semantic/cache.dart`)
- Load all 41,995 vectors from `verse_embeddings` table
- `Float32List` storage (768D each)
- Optional lazy loading for mobile memory constraints

**Cosine Similarity** (`semantic/similarity.dart`)
- `cosineSimilarity()` - line 1313

**Sinkhorn WMD** (`semantic/wmd.dart`)
- Port lines 1340-1390
- Chamfer distance + Earth Mover's Distance
- Used for embedding phrase matching

### 2.4 Graph Propagation (`graph/propagation.dart`)

**PageRank** (`graph/pagerank.dart`)
- `normalizedPageRankScore()` - line 2046
- Uses pre-baked `verse_pagerank` table
- Normalize by P95

**Query-Personalized PPR** (`graph/ppr.dart`)
- `queryPPR()` - lines 2187-2279
- Intent-specific profiles with alpha 0.72-0.84

**Random Walk with Restart** (`graph/rwr.dart`)
- `rwrStmt` queries `verse_rwr` table - lines 1509-1518

**Spectral Embeddings** (`graph/spectral.dart`)
- `verse_spectral` 50D embeddings - lines 3005-3035

### 2.5 Scoring (`scoring/specificity.dart`)

**Specificity Score** (`scoring/specificity.dart`)
- Lines 3135-3156
- T1-T5 tier assignment based on evidence quality
- Calibration via PAV curves

### 2.6 Fusion (`fusion/rrf.dart`)

**Reciprocal Rank Fusion** (`fusion/rrf.dart`)
- `reciprocalRankFusion()` - lines 2073-2106
- RRF_K = 60

**MMR Rerank** (`fusion/mmr.dart`)
- `mmrRerank()` - lines 2110-2164

### 2.7 Expansion (`expansion/pmi.dart`)

**PMI Expansion** (`expansion/pmi.dart`)
- `expandWithPmi()` - lines 1973-2002

**Concept Expansion** (`expansion/concepts.dart`)
- `expandWithConcepts()` - lines 2489-2500

### 2.8 Optimizer (`optimizer/adam.dart`)

**Learned Weights** (`optimizer/adam.dart`)
- Adam optimizer: beta1=0.9, beta2=0.999, lr=0.01

**Calibration Curves** (`optimizer/calibration.dart`)
- PAV algorithm - lines 1044-1079

---

## Phase 3: Reader Mode UI (Days 15-18)

### 3.1 Material Design Screens

**Reader Screen** (`reader_mode/screens/reader_screen.dart`):
- Continuous chapter reading with verses grouped by paragraph
- `segmentVerseText()` breaks verses at 200 words (mirroring backend)
- Bottom navigation: previous/next chapter, search, bookmark
- Floating action button: quick highlight menu (4 Material colors)
- Two-finger tap: add bookmark
- Long press: highlight menu with color selection
- Edge swipe: previous/next chapter
- Pinch zoom: text size adjust
- Offline indicator: green dot in app bar

**Search Screen** (`reader_mode/screens/search_screen.dart`):
- Live search with 300ms debounce
- Suggestion chips from FTS5 vocabulary below search bar
- Results show verse reference, text snippet, `_specificity_score`, `_relevance_probability`
- Debug overlay on tap: breakdown of scoring components (fts, phrase, semantic, PPR, WMD)
- Cluster facets as horizontally scrollable chips
- No network indicator: "offline mode" banner
- Semantic mode toggle (~ prefix) in keyboard actions

**Bookmarks Screen** (`reader_mode/screens/bookmarks_screen.dart`):
- List cards showing verse preview with highlight color
- Sort options: date (newest), book order, highlight color
- Delete action via swipe-to-dismiss
- Empty state: illustration + "search to add bookmarks"

**Highlights Screen** (`reader_mode/screens/highlights_screen.dart`):
- Filter bar: 4 color filter chips (yellow, green, blue, pink)
- Grouped by book with chapter counts badges
- Verse previews inline with context
- Statistics header: reading streak, coverage %, total highlights

**Settings Screen** (`reader_mode/screens/settings_screen.dart`):
- Theme section: light, dark, system
- Translation section: dropdown with 12 options
- Text settings: size slider, line height selector
- Offline status: bundled DB version, last update date
- Debug section: toggle score overlays, show raw math values, test HNSW speed

**Verse Context Bottom Sheet** (`reader_mode/widgets/verse_context_sheet.dart`):
- Modal sheet triggered from verse long-press
- Cross references list with previews
- Chapter summary from AI-generated content
- AI insight snippet from `verse_summaries`
- Share action: copy verse, share image, copy link

### 3.2 Adaptive Layout

**Phone (Portrait)**:
- Single column reading view
- Navigation drawer via hamburger menu
- Floating buttons overlay content

**Phone (Landscape)**:
- Dual-pane optional: English + translation side-by-side

**Tablet**:
- Split pane permanent: chapters (left) / verses (right)
- search bar always visible in app bar
- Multi-select for batch highlight/delete

### 3.3 State Management

```dart
// Reading state with offline-first persistence
@freezed
class ReadingState with _$ReadingState {
  final int? currentVerseId;
  final int? currentChapterId;
  final List<int> history;
  final Map<int, int> highlights; // verseId -> color
  final Set<int> bookmarks;
  final int? lastRead;
}

// Search state with intelligence visibility
@freezed
class SearchState with _$SearchState {
  final String query;
  final List<SearchResult> results;
  final int? selectedIndex;
  final IntentClass intent;
  final double confidence;
  final bool showDebugOverlay;
  final Map<String, dynamic> scoreBreakdown;
  final List<String> facets;
}

// Providers
final readingProvider = StateNotifierProvider<ReadingNotifier, ReadingState>();
final searchProvider = StateNotifierProvider<SearchNotifier, SearchState>();
final settingsProvider = StateNotifierProvider<SettingsNotifier, AppSettings>();
```

### 3.4 Performance Optimizations

- Lazy load embeddings (only for visible + prefetch)
- Precompute HNSW neighbors on background isolate
- LRU cache for search results (30 entry limit)
- Database indexes pre-loaded on app start
- Cold start: show splash until HNSW loads

### 3.5 Offline Strategies

- All databases cached in app documents
- SQLite in read-only mode for performance
- User data (bookmarks/highlights) in separate writeable DB
- Queue reading events for sync when network available
- Last 3 search queries cached in memory

---

## Phase 4: Benchmark Parity (Days 19-21)

Mirror all backend tests:

| Test | Expected | Location |
|------|----------|----------|
| Reference search | John 3:16 → exact match | `test/benchmark_test.dart` |
| Phrase search | "faith without works" → phrase match | `test/benchmark_test.dart` |
| NEAR recovery | "ten thousand fallen him in midst" → Mormon 6 | `test/benchmark_test.dart` |
| Specificity ranking | High scores first | `test/benchmark_test.dart` |
| KJV spellings | neighbor ↔ neighbour | `test/normalization_test.dart` |
| Anchor detection | Long queries extract salient terms | `test/anchor_test.dart` |
| WMD matching | Word order variations handled | `test/wmd_test.dart` |
| Query intent | "faith" → conceptual, "John 3:16" → reference | `test/intent_test.dart` |
| RRF fusion | Multiple sources boost scores | `test/fusion_test.dart` |
| Calibration | Low scores boosted correctly | `test/calibration_test.dart` |

---

## Phase 5: Advanced Mathematical Optimizations (Days 12-14)

### 5.1 Vector Math Improvements

**Cosine Similarity Optimization**:
- SIMD-friendly dot product using `dart:ffi` for ARM NEON
- Sqrt approximation: `1 / sqrt(x)` via fast inverse sqrt (Quake algorithm)
- Vector normalization cached as pre-computed magnitude squared

**Embedding Storage Optimization**:
- Quantize to int8 for 75% memory reduction (4 bytes → 1 byte per dimension)
- Dequantization: `float = int8 * scale + offset` 
- Int8 dot product for early candidate filtering before full precision

### 5.2 HNSW Algorithm Enhancements

**Graph Traversal Optimization**:
- Replace `Math.floor(-Math.log(Math.random()) * M_INV)` with faster approximation
- Cache entry points per layer to avoid repeated random generation
- BFS-style visited set using `Uint32List` bitset instead of Set for 4x speed

**Candidate Selection Improvements**:
```dart
// Backend uses 0.05 floor; mobile can use adaptive floor
// based on query entropy and corpus statistics
double adaptiveFloor(List<double> similarities) {
  final mean = similarities.reduce((a, b) => a + b) / similarities.length;
  final variance = similarities.map((s) => pow(s - mean, 2)).reduce((a, b) => a + b) / similarities.length;
  return max(0.03, mean - 0.5 * sqrt(variance)); // 1-sided statistical cutoff
}
```

### 5.3 Sinkhorn WMD Optimizations

**Chamfer Distance Improvements**:
- Use k-d tree for token vector nearest neighbor search (k=5)
- Early termination when distance > threshold
- Cache token vectors in `Float32List` single block

**Earth Mover's Distance Enhancements**:
- Sparse cost matrix for non-overlapping tokens
- Upper bound estimation to prune expensive calculations
- Parallel row processing on multiple isolates

### 5.4 Scoring Function Refinements

**Specificity Score Precision**:
- Use cubic instead of sigmoid for specificity gating (smoother gradients)
- Precompute tier baselines with lookup table
- Vectorize batch scoring for MMR candidates

**Relevance Probability Optimization**:
```dart
// Logistic function: avoid exp() overflow for large logits
double stableSigmoid(double logit) {
  if (logit >= 0) return 1.0 / (1.0 + exp(-logit));
  final expVal = exp(logit);
  return expVal / (1.0 + expVal);
}
```

### 5.5 Memory-Efficient Graph Propagation

**Sparse Matrix Representation**:
- PPR adjacency as CSR (Compressed Sparse Row) format
- Spectral vectors stored as `Float32List` with pooling
- Cache frequently accessed graph neighborhoods

**Numerical Stability**:
- Prevent rank score collapse via log-space summation
- Use double precision for propagation accumulation
- Clamp cosine outputs to [0,1] before sigmoid

### 5.6 Compute Scheduler

**Isolate-based Parallelization**:
- Background isolate for HNSW queries
- Separate isolate for WMD calculations
- Main isolate for UI updates, use `compute` for heavy math

**Lazy Evaluation**:
- Compute `_qpprScore` only for top 50 candidates
- Defer WMD until user pauses on search result
- Batch database queries for related verse metadata

## Critical Mathematical Guarantees

### No Intelligence Compromises

| Feature | Implementation | Lines |
|---------|---------------|-------|
| No ZCA | Raw L2-normalized vectors only | 2232-2241 |
| Co-occurrence penalty | Pure observed probability | 1605-1630 |
| No hardcoded synonyms | PMI from corpus only | 1973-2002 |
| Specificity-first | Tier ordering enforced | 3126-3169 |
| Weak structure prior | Max 0.07, intent-filtered | 2058-2069 |

### Performance Requirements

- Search latency: < 200ms for cached queries
- First search after cold start: < 5s
- Memory: < 200MB with full embedding cache
- Offline: 100% functionality without network

---

## Deliverables Timeline

| Day | Milestone |
|-----|-----------|
| 1 | Project scaffold, PLAN.md, resource copy |
| 2-4 | Normalization + FTS5 port |
| 5-8 | Semantic search (HNSW, embeddings) + optimizations |
| 9-11 | Graph propagation (PPR, RWR, spectral) + sparse matrices |
| 12-14 | Scoring pipeline + fusion + mathematical refinements |
| 15-16 | Reader UI screens + gestures |
| 17-18 | Search UI + debug overlays |
| 19-20 | Benchmark parity tests |
| 21 | Release candidate |

---

## Verification Commands

```bash
# Verify resources copied (excluding waray)
ls -la assets/resources/db/*.db

# Run all benchmarks
flutter test test/benchmark_test.dart

# Profile memory
flutter run --profile

# Test ONNX loading
flutter run --dart-define=ONNX_DEBUG=true
```
