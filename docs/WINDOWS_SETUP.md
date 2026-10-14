# Windows development setup

This project is now being prepared on Windows, not Linux. Historical Linux settings are archived under `docs/archive/`; do not restore them as active SDK paths.

## Flutter installation

Installed 2026-10-11 from the official Flutter stable branch:

- SDK: `<tools>\flutter`
- Flutter: 3.47.7
- Framework revision: `abaf9c523780a608bd46686fd5e53740a07077f8`
- Dart: 3.13.5 (included with Flutter)
- Windows desktop support enabled; analytics disabled.
- SDK `bin` added to the Windows user PATH. Restart terminals/editor to inherit it.

In an existing PowerShell session, use:

```powershell
$env:Path = '<tools>\flutter\bin;' + $env:Path
flutter --version
flutter doctor -v
flutter devices
```

## Native Windows compiler

Microsoft Visual Studio Build Tools 2022 was installed with owner approval. The installer exited successfully, and `flutter doctor -v` now passes the Visual Studio/Windows compiler checks:

- Build Tools 2022 17.14.41; installation version 17.14.37710.0.
- Installation: `C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools`.
- Windows SDK: 10.0.26100.0.
- Only the Android SDK remains missing in Flutter doctor.

The command used is:

```powershell
winget install --id Microsoft.VisualStudio.2022.BuildTools --exact --source winget --accept-source-agreements --accept-package-agreements --disable-interactivity --silent --override "--quiet --wait --norestart --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
```

Flutter's installed detection code accepts the Build Tools `VCTools` workload as well as Visual Studio's `NativeDesktop` workload. VS Code by itself does not provide the compiler. No automatic reboot is requested.

## Application checks

From the app directory:

```powershell
flutter pub get
flutter analyze
flutter test
```

Dependency resolution regenerates `.dart_tool/package_config.json` for Windows. Do not manually rewrite generated package-cache paths. The pre-setup lockfile and generated state remain in the external Phase 0 backup.

The Windows runner has been generated using `flutter create --platforms=windows --no-pub --no-overwrite .`; all previously existing lib/test files were hash-checked as unchanged. Once the compiler is ready and legacy application errors have been resolved:

```powershell
flutter build windows
flutter run -d windows
```

Toolchain readiness does not establish that the legacy app compiles or that Experiment D is implemented. Track actual command results in DEVLOG. Keep models and databases external to source control.

## Android is separate

The Android SDK is not installed yet. Its absence does not block Windows desktop compilation. Keep the old Linux `sdk.dir` disabled; configure the real Windows Android SDK when preparing Android builds.

## Initial app verification results

- `flutter pub get`: passed; generated package configuration now uses Windows paths. Updated four lockfile dependencies (matcher, meta, test_api, vector_math) and Flutter automatically added analyzer exclusions for build/android directories.
- `android/local.properties`: Flutter regenerated the active flutter.sdk with the installed Windows location. Linux values remain in the historical archive, not active assignments.
- `flutter analyze --no-pub`: 38 issues, including four errors: undefined SearchPipeline at search_screen.dart lines 21/39 and undefined _sqrt at embedding_loader.dart lines 371/372. These are legacy source problems; source files were not rewritten during setup.
- `flutter test --no-pub`: suite failed during compilation/loading, including the widget test's dependency on the missing SearchPipeline. Eleven legacy unit-test cases reported passing, but that does not make the overall suite pass.
- `flutter test --no-pub test/benchmark_test.dart`: isolated rerun passed all 11 tests. These validate legacy utilities only, not Experiment D.
- Preserved the original Android migration entry in `.metadata` alongside the generated Windows entry; no Android runner source was replaced.
- A separate minimal project at `<tools>\scriptura_windows_probe_20261011` successfully built with `flutter build windows --release --no-pub` (exit 0). Output: `build\windows\x64\runner\Release\scriptura_windows_probe.exe`. This verifies native release compilation, not GUI execution or the scripture app's functionality. The executable was not launched.

Sources: [Flutter Windows setup](https://docs.flutter.dev/platform-integration/windows/setup), [Flutter installation](https://docs.flutter.dev/install/manual).
