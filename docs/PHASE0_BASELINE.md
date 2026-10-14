# Phase 0 baseline — 2026-10-11

Status: preservation and initial environment inventory complete; Phase 0 is not complete.

## Recovery copy

Before editing application files, copied the full app directory to:

`<projects>\scriptura\app-backups\scriptures_reader_mobile-before-phase0-20261011`

Robocopy reported 175 files copied with no failures. All 175 copied files matched their source SHA-256. This includes legacy assets, user-data.db, WAL/SHM files, and generated build files. No source files were deleted or moved. The copy is outside the app and must remain private; it is not a model distribution artifact.

This is a file-level recovery copy, not certification of SQLite transactional integrity. Before migration, validate databases on copies and use SQLite's backup API for any live database. Preserve originals and journals until that work passes.

## Development machine

- Windows 11 Home Single Language, version 10.0.26200.
- AMD Ryzen 5 5500U with Radeon Graphics.
- OS-reported physical memory: 7,866,093,568 bytes (approximately 7.3 GiB).
- Available C: storage before backup: approximately 61.4 GiB.
- Git available at `C:\Program Files\Git\cmd\git.exe`.
- Flutter, Dart, ADB, and CMake were not found in this shell's PATH.
- Flutter not found under C:\src, C:\flutter, C:\dev, C:\tools, or the checked user flutter/development locations.
- Default user Android SDK, standard Android Studio directory, and Visual Studio Installer's vswhere were not found. This does not rule out custom installations.

`android/local.properties` and `.dart_tool/package_config.json` refer to `<home>/...`; they are stale Linux-machine configuration, not working Windows toolchain evidence. Do not rely on previous build outputs as a current passing build.

## Source protection

The app has no local `.git` directory. Added ignore rules for legacy resources, local artifact staging, generated model/index files, databases and journals, environment secrets, and Python tooling caches. Fonts/icons and source files are not blanket-excluded.

No Git initialization, staging, commit, remote creation, or push performed in this milestone. A future baseline must use an explicit code-only allowlist and inspect staged paths. No model/database imports, dependency installs, platform scaffolding, or search implementation changes performed yet.

## Remaining Phase 0 work

1. Locate custom toolchains or arrange installation; run Flutter doctor and establish actual analysis/test/build results.
2. Establish the code-only Git baseline; select a remote only with owner direction.
3. Verify and import only the artifact handoff allowlist, retaining original bundles.
4. Add Windows scaffolding after the baseline; review generated changes.
5. Verify the V29 through available device tools before claiming hardware qualification.

Next implementation milestone: artifact validator and executable Experiment D reference (PLAN Phase 1). The desktop memory inventory makes peak-memory measurement important; no mobile/desktop performance claim is established.
