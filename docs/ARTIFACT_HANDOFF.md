# Artifact handoff and import runbook

Verified 2026-10-11. Companion to [PLAN.md](../PLAN.md). This document identifies existing inputs and proposed outputs. **No model/database copying or extraction was performed as part of writing the plan.** Commands below are for the later implementation phase.

## 1. Exact locations

```text
Source artifact directory:
<projects>\scriptura

Application source directory:
<projects>\scriptures_reader_mobile

Research code (source/reference, no longer a full live data workspace):
D:\scriptures_pandora_genome_model

Proposed development import directory, not created yet:
<projects>\scriptures_reader_mobile\.artifact-staging\import-application-v1
```

Never copy the entire `scriptura` directory. It also contains research archives, operational logs, and a private Git-history backup that are NOT application assets. Original artifacts stay in place; copy, do not move. Production installs use platform application-support storage, not any of these development paths.

## 2. Verified input allowlist

Sizes are exact bytes; rounded sizes elsewhere are estimates. All seven file hashes below were computed from the current local files, not merely copied from their filenames.

| Relative to source directory | Bytes | Later staging destination |
| --- | ---: | --- |
| `bge-m3-pinned-5617a9f6.zip` | 2,295,424,059 | `archives/bge-m3-pinned-5617a9f6.zip` |
| `scripture-genome-question-hidden4096-full.zip` | 128,824,366 | `archives/scripture-genome-question-hidden4096-full.zip` |
| `scripture-genome-question-hidden4096-optimized.zip` | 19,681,169 | `archives/scripture-genome-question-hidden4096-optimized.zip` |
| `scripture-retrieval-english-v1.zip` | 193,707,772 | `archives/scripture-retrieval-english-v1.zip` |
| `application_databases/scriptures_genome.db` | 219,938,816 | `databases/scriptures_genome.db` |
| `application_databases/questions_genome.db` | 285,589,504 | `databases/questions_genome.db` |
| `application_databases/scripture_genome_raw.db` | 860,291,072 | `databases/scripture_genome_raw.db` |

Also copy `application_databases/manifest.json` and `application_databases/README.md` alongside the DB copies. Their build notes are useful, but the README's suggestion of future FAISS indexes is historical; this plan starts with exhaustive vector scans.

```text
bge-m3-pinned-5617a9f6.zip
a656b35429255b1bd5877bf792e6e2c7bd65be192e3ac00b3dbdfbecdacd4883

scripture-genome-question-hidden4096-full.zip
344f3199f4270a5dcba173aee8882a99d57c77bde27072b325b54b6e2bcefdbb

scripture-genome-question-hidden4096-optimized.zip
9182e759e8304ca291256c9b81991cf3740de92311302a304ce127d10d678ece

scripture-retrieval-english-v1.zip
7e577d597a5b521b71d85fdebee612e74dfeff07f64c7a958d33bf4bacdb9d6d

scriptures_genome.db
e8ca90e1e404060f6bde43deaabe39450bc3b0f8f4511d4f4eb62b6ac23c9c36

questions_genome.db
19b42214a860546b2fc11b1b5f94e7fda57b31b90768847fde2d0f666ec9c99c

scripture_genome_raw.db
d0f8d39a855b1d9284fcc442c2b592342a7750a24152adf7cadd10c949362636
```

Outer ZIP hashes, inner file hashes, and checkpoint hashes are different things. Never compare one kind against another and conclude corruption.

## 3. What is inside each ZIP

### Base encoder

ZIP root: `bge-m3-pinned/`

- `pytorch_model.bin` — full base weights, approximately 2.27 GB.
- `tokenizer.json`, `tokenizer_config.json`, `special_tokens_map.json`, `sentencepiece.bpe.model` — preserve the exact tokenizer configuration.
- `config.json`, pooling/Sentence Transformers configuration files.
- `sparse_linear.pt` — BGE sparse projection, required for Experiment D.
- `colbert_linear.pt` — BGE ColBERT projection, required for Experiment D.
- `manifest.json` — inner inventory/checksums.

Pinned revision: `5617a9f61b028005a4858fdac845db406aefb181`. No verified quantized base or mobile ONNX graph is in this ZIP. Do not load an unrelated old `assets/resources/.../model_quantized.onnx` as a substitute. Obtain/preserve upstream license notices before redistributing derived base exports; do not assume this archive contains every necessary notice.

### Full head

ZIP root: `scripture-genome-question-hidden4096-full/`

- `head_fp32.npz` — inference weights, keys `0.weight`, `0.bias`, `2.weight`, `2.bias`.
- `best.pt` — full training checkpoint; reference/export only, not needed on the phone.
- `gene_ids.txt`, `head_card.json`, `runtime_config.json`, `validation_q250.json`, `manifest.json`.

Weight shapes: `[4096,1024]` and `[568,4096]`; biases `[4096]` and `[568]`. Head architecture is GELU hidden activation and Sigmoid output. Checkpoint SHA-256:

```text
5a68ef73167f48899c927dfb5e25dfe8ff50d0b8e8310cd6f3ff3c93b8bf9952
```

### Optimized head

ZIP root: `scripture-genome-question-hidden4096-optimized/`

- `head_fp16.npz`: `w0`, `b0`, `w1`, `b1`; weights FP16, biases FP32.
- `head_int8.npz`: same layer keys plus `scale0`, `scale1`; per-output-row scales. Reconstruction is `weight = int8_weight * scale[:, None]`; activations remain floating point in the reference loader.
- Same supporting config/gene/report files, with export-specific card/manifest.

These are NPZ arrays, not ONNX, Safetensors, or TorchScript. The research repository's `scripts/model_bundle_runtime.py` expects other bundle formats; it is not a drop-in loader for these NPZ files. Use the actual array keys and check shapes. The format-aware example in `D:\scriptures_pandora_genome_model\docs\huggingface\README.md` is a starting reference.

### English retrieval assets

ZIP root: `scripture-retrieval-english-v1/`

| File | Contract |
| --- | --- |
| `verse_ids.npy` | Explicit row → canonical verse ID mapping |
| `dense_embeddings.f16.npy` | `[41995,1024]`, FP16 passage dense vectors |
| `genome_vectors.f16.npy` | `[41995,568]`, unweighted normalized-score verse genomes |
| `weighted_genome_embeddings.f16.npy` | `[41995,568]`, reference retrieval-weighted vectors |
| `sparse_index.csr.npz` | `[41995,250002]`, 1,156,270 nonzero learned token weights |
| `scripture_text.jsonl` | Candidate text used in retrieval; preserve exactly for reference encoding |
| `gene_ids.txt` | Feature order; must match the head |
| `retrieval_config.json`, `manifest.json` | Config, dimensions, row identity, inner hashes |

**No permanent ColBERT token vectors are included.** Building them is Phase 3, not an already-finished task.

`verse_ids.npy` file SHA-256 is `7012e3352f9a904e3e7bf92d4ca89cc39863f84c1d332fee0278aa00c444568b`. The config's `verse_order_sha256` is a semantic order hash, not that file hash; reproduce its canonical serialization before using it as a validator. The shared `gene_ids.txt` file SHA-256 is `16878f92a2f6434b39ef6d68c633f2cd815751f2b4be8767a309e32442baf195`.

Load NumPy files with `allow_pickle=False`; map large uncompressed matrices where practical. Conversion to native formats must be lossless before precision experiments.

## 4. Database contracts and verification

The existing DBs are already the required normalized application format. Do not regenerate them from CSVs simply to start the app.

- `scriptures_genome.db`: 41,995 rows in `scripture_vectors`; text in eight `scriptures_<language>` tables. Each text row has `verse_id, scripture_text, reference, shortened, book, chapter, verse`. `scripture_text_sources` tracks source and quality tier; `language_coverage` identifies incomplete languages.
- `questions_genome.db`: 47,400 question vectors, 47,400 rows per question language, 232,310 weighted answer edges, 262 collections, and 45,850 collection memberships. Not every question is necessarily represented by those memberships; do not infer full coverage from collection counts.
- `scripture_genome_raw.db`: 41,995 rows in `verse_genome_raw(verse_id, genome_raw_json)`; optional diagnostic content.

Read-only validation on staged copies must include SQLite integrity/foreign-key checks, BLOB byte size and endianness, finite `[0,1]` values, unique IDs, cross-file answer-edge references, gene metadata, and exact retrieval-ID mapping. Cross-file constraints require explicit checks. Inspect DB metadata before assuming schema/gene versions.

## 5. Later copying: safe development procedure

### Before running anything

1. Complete Phase 0 backup. No data should be removed to make room without the owner's direction.
2. Add the following rules to the app's `.gitignore` before import (this planning change has NOT added them):

```gitignore
/.artifact-staging/
/generated-artifacts/
/local-benchmarks/
```

Audit existing `assets/` separately before the first Git commit; the rules above do not automatically exclude old binary files. Use a code-only allowlist.

3. Check development disk space for roughly 4 GB of source copies, extraction, ONNX exports, ColBERT indexes, and rollback. Reserve substantially more than source sizes; calculate exact required space before creating large generated files. This is desktop preparation, not a promise of the mobile installation size.
4. Confirm the source DBs are static snapshots, not currently being modified by another process. Do not use this raw copy procedure for a live user database.

### Copy only the allowlist (PowerShell; run later)

This fails if the destination already exists; it never overwrites or deletes a previous import. If interrupted, inspect the partial directory and use a new clearly named import directory or explicitly authorized cleanup.

```powershell
$ErrorActionPreference = 'Stop'
$artifactSource = '<projects>\scriptura'
$appSource = '<projects>\scriptures_reader_mobile'
$importRoot = Join-Path $appSource '.artifact-staging\import-application-v1'

if (Test-Path -LiteralPath $importRoot) {
    throw 'Import destination already exists. Inspect it; do not overwrite it.'
}

$items = @(
    @{ Source='bge-m3-pinned-5617a9f6.zip'; Folder='archives'; Hash='a656b35429255b1bd5877bf792e6e2c7bd65be192e3ac00b3dbdfbecdacd4883' },
    @{ Source='scripture-genome-question-hidden4096-full.zip'; Folder='archives'; Hash='344f3199f4270a5dcba173aee8882a99d57c77bde27072b325b54b6e2bcefdbb' },
    @{ Source='scripture-genome-question-hidden4096-optimized.zip'; Folder='archives'; Hash='9182e759e8304ca291256c9b81991cf3740de92311302a304ce127d10d678ece' },
    @{ Source='scripture-retrieval-english-v1.zip'; Folder='archives'; Hash='7e577d597a5b521b71d85fdebee612e74dfeff07f64c7a958d33bf4bacdb9d6d' },
    @{ Source='application_databases\scriptures_genome.db'; Folder='databases'; Hash='e8ca90e1e404060f6bde43deaabe39450bc3b0f8f4511d4f4eb62b6ac23c9c36' },
    @{ Source='application_databases\questions_genome.db'; Folder='databases'; Hash='19b42214a860546b2fc11b1b5f94e7fda57b31b90768847fde2d0f666ec9c99c' },
    @{ Source='application_databases\scripture_genome_raw.db'; Folder='databases'; Hash='d0f8d39a855b1d9284fcc442c2b592342a7750a24152adf7cadd10c949362636' }
)

# Validate ALL originals before copying anything.
foreach ($item in $items) {
    $sourcePath = Join-Path $artifactSource $item.Source
    if ((Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash -ne $item.Hash) {
        throw "Source hash mismatch: $sourcePath"
    }
}

New-Item -ItemType Directory -Path $importRoot | Out-Null
foreach ($item in $items) {
    $sourcePath = Join-Path $artifactSource $item.Source
    $targetDirectory = Join-Path $importRoot $item.Folder
    New-Item -ItemType Directory -Path $targetDirectory -Force | Out-Null
    $targetPath = Join-Path $targetDirectory (Split-Path $sourcePath -Leaf)
    Copy-Item -LiteralPath $sourcePath -Destination $targetPath
    if ((Get-FileHash -LiteralPath $targetPath -Algorithm SHA256).Hash -ne $item.Hash) {
        throw "Copied hash mismatch: $targetPath"
    }
}
foreach ($name in @('manifest.json', 'README.md')) {
    $sourcePath = Join-Path $artifactSource "application_databases\$name"
    $targetPath = Join-Path $importRoot "databases\$name"
    Copy-Item -LiteralPath $sourcePath -Destination $targetPath
    if ((Get-FileHash -LiteralPath $sourcePath).Hash -ne (Get-FileHash -LiteralPath $targetPath).Hash) {
        throw "Metadata copy mismatch: $name"
    }
}
Write-Host "Verified import copied to $importRoot. Originals unchanged."
```

### Extract verified archives (Python; run later)

Use a ZIP64-capable streaming extractor: the base contains an individual weight file larger than 2 GB. The following extracts only the four known ZIPs into a new directory and checks member paths before extraction. The archive hash verification above is a prerequisite. Inner-manifest validation is still required afterward.

```python
from pathlib import Path
import stat
import zipfile

root = Path(r'<projects>\scriptures_reader_mobile\.artifact-staging\import-application-v1')
output = root / 'extracted'
archives = [
    'bge-m3-pinned-5617a9f6.zip',
    'scripture-genome-question-hidden4096-full.zip',
    'scripture-genome-question-hidden4096-optimized.zip',
    'scripture-retrieval-english-v1.zip',
]
if output.exists():
    raise RuntimeError('Extraction destination already exists; inspect before retrying')

# Preflight every member before creating any output.
seen = set()
for name in archives:
    with zipfile.ZipFile(root / 'archives' / name) as archive:
        for entry in archive.infolist():
            destination = (output / entry.filename).resolve()
            if not destination.is_relative_to(output.resolve()):
                raise ValueError(f'Unsafe ZIP member: {entry.filename}')
            if stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError('ZIP links are not allowed')
            key = str(destination).casefold()
            if key in seen:
                raise ValueError(f'Duplicate destination: {entry.filename}')
            seen.add(key)

output.mkdir(parents=True)
for name in archives:
    with zipfile.ZipFile(root / 'archives' / name) as archive:
        archive.extractall(output)
print('Extracted. Validate inner manifests before use:', output)
```

This procedure is for these hash-verified developer bundles, not a complete untrusted public-import implementation. The production importer additionally needs expansion limits, trusted/signed manifest policy, expected-file allowlists, and recovery behavior from PLAN section 9.

Do not copy extracted Python/PyTorch training files directly into a phone package. Phase 2 creates native-runtime-compatible artifacts. Keep `best.pt`, full research CSVs, and training caches outside the shipping app.

## 6. Proposed outputs still to build

| Output | Generated from | Reason |
| --- | --- | --- |
| Multi-output FP32 base ONNX + external data | Pinned base/projection weights | Portable reference inference |
| INT8/mixed-precision base ONNX | Validated reference export, training-only calibration if needed | Candidate mobile deployment |
| Head ONNX/native parameter pack | Selected NPZ weights | App-compatible inference, same 568 outputs |
| Native dense/genome files + row map | Existing retrieval arrays | Efficient native reads without per-row SQL |
| Sparse posting lists | Existing CSR weights/token IDs | Efficient learned lexical scoring |
| ColBERT token shards + offsets/counts | Exact retrieval text + pinned base | Avoid hundreds of passage encodings per phone query |
| Language phrase indexes | Actual scripture DB text | Model-free phrase search |
| Navigation catalog | Canonical book/chapter metadata | Correct ordering and reference lookup |
| Release compatibility manifest | All generated artifacts/configs/runtime requirements | Safe installation and reproducibility |

Proposed filenames and formats must be finalized in Phase 1/2 and tested before publishing. No completed mobile model/index export is claimed here.

The release manifest must include: manifest schema/version, base revision and tokenizer hash, head checkpoint/export hash, gene-order hash, exact corpus/text-source identity, row-map file hash, feature weights, fusion weights and standardization scope, candidate budgets, precision on both query/passage sides, token-retention rules, tensor dimensions, file size/hash, minimum engine version/platform, package dependencies, download/unpacked sizes, and required license notices.

## 7. Reference code and caution about older defaults

Under `D:\scriptures_pandora_genome_model`:

- `notebooks/kaggle_cells/end_to_end_search_cell.py`: head/dense/genome preparation and weighted cosine reference.
- `notebooks/kaggle_cells/bge_m3_four_signal_search_cell.py`: Experiment D arithmetic and masking.
- `notebooks/kaggle_cells/four_signal_validation_cell.py`: matched evaluation methods and question-cluster reporting.
- `scripts/train_genome_head.py`: actual head architecture/loss/training partition behavior.
- `scripts/build_app_databases.py`: source DB construction/schema reference; archived data must be restored if rebuilding.
- `docs/huggingface/README.md`: format-aware NPZ head loader and selected model card.

Do not execute old notebook cells unmodified: globals, paths, head size/checkpoint defaults may be stale. Especially do not pick an 8192 model based on a filename containing “latest.” Selected bundle config wins; saved reference tests arbitrate numerical behavior.

## 8. Excluded/private material

Do not import or publish these as app assets:

- `scripture-genome-git-before-history-cleanup-2026-10-08.bundle` — private historical data backup.
- `scripture-operational-logs-2026-10-08.zip` — operational logs, not runtime data.
- `.env`, tokens, signing keys, user data, training caches, unrelated downloads.
- `scripture-genome-research-2026-10-08.zip` — research recovery only; restore specific inputs in a separate workspace when needed for evaluation/rebuilds, never indiscriminately into the app.
- Existing app `assets/resources` models/DBs and `old_app_reference` data — legacy references, not recent source artifacts.

Preserve these files; exclusion is not permission to delete. This handoff directs later copying of the seven allowlisted inputs only.
