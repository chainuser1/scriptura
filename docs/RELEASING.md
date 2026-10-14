# Releasing

Releases are GitHub releases. The goal is that the newest installers are always reachable at a fixed address and that the
app can tell when it is out of date.

## Stable names

GitHub serves `https://github.com/<owner>/<repo>/releases/latest/download/<asset>` for the newest release **only when the
asset has the same file name in every release**. Each release therefore carries both:

| Asset | Purpose |
|---|---|
| `Scriptura-Setup.exe`, `Scriptura.apk` | stable names: the "latest" links |
| `Scriptura-Setup-<version>.exe`, `Scriptura-<version>.apk` | the same files with the version, for an exact install |
| `SHA256SUMS.txt` | checksums of the four files |

## Signing

**Android.** Updates only install over an earlier build when both are signed with the same key, so the published APK must be
signed with a key you keep. Create it once and back it up somewhere safe (losing it means users must uninstall to update):

```
keytool -genkeypair -v -keystore scriptures-release.jks -alias scriptures -keyalg RSA -keysize 4096 -validity 10000
```

Put the file outside the repository and create `android/key.properties` (git-ignored):

```
storeFile=C:/keys/scriptures-release.jks
storePassword=...
keyAlias=scriptures
keyPassword=...
```

Without that file the release build is signed with the machine's debug key, which is fine for testing on your own phone.

**Windows.** The installer is not code-signed; SmartScreen warns on first run. Signing needs a code-signing certificate
(`signtool sign /fd SHA256 ...` on `Scriptura-Setup.exe` before staging).

## Cutting a release

1. Set the version in `pubspec.yaml` (`version: 1.2.0+3`) and the same value in `lib/app/version.dart` (`kAppVersion`).
2. Rebuild everything: `cargo build --release` in `engine/`, `python tool/build_engine_android.py`,
   `flutter build apk --release --target-platform android-arm64`, `python tool/build_installer.py`.
3. Run the tests (`flutter test --concurrency=2`, `cargo test --release`).
4. Stage the assets: `python tool/make_release.py --notes "What changed"`. It refuses to run when the two versions differ and
   writes `generated-artifacts/release-assets/<version>/` plus the exact commands below.
5. Publish (needs a GitHub remote and the GitHub CLI):

   ```
   git tag v<version>
   git push origin v<version>
   gh release create v<version> generated-artifacts/release-assets/<version>/* --title "Scriptura <version>" --notes-file generated-artifacts/release-assets/<version>/RELEASE_NOTES.md --latest
   ```

## Update check in the app

When `kReleasesApi` in `lib/app/version.dart` is set to
`https://api.github.com/repos/<owner>/<repo>/releases/latest`, Settings shows **Check for updates**. It makes one anonymous
request, compares the release tag with `kAppVersion`, and offers the installer for the platform. It is empty until the
repository exists, and while it is empty the app never contacts a release server.

## Data is separate

Releases contain the app only. Scripture text and search data are downloaded by the app from the data bucket
(`kDefaultDataAddress`), so a new app release does not re-upload gigabytes. Changing the data format is a separate,
versioned step documented in `docs/ARTIFACT_LAYOUT.md`.
