import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';

import 'app/shell.dart';
import 'app/theme.dart';
import 'app_controller.dart';
import 'features/welcome/welcome_screen.dart';
import 'services/engine/benchmark.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final support = await getApplicationSupportDirectory();
  Directory? dev;
  if (Platform.isAndroid) {
    final ext = await getExternalStorageDirectory();
    if (ext != null) dev = Directory('${ext.path}/dev-packs');
  }
  final app = AppController(root: Directory(support.path), devPacks: dev);
  runApp(ScripturesReaderApp(app: app));
  await app.load(); // text and catalog first, then the engine in the background
  // First run: fetch whatever is missing from the published address (a no-op when everything is installed). A
  // side-loaded `dev-packs/data-address` points it at a test server instead and mirrors progress to setup-status.txt.
  String? address;
  if (dev != null) {
    final f = File('${dev.path}/data-address');
    try {
      if (f.existsSync()) address = f.readAsStringSync().trim();
    } on Object {
      // unreadable override: use the published address
    }
    if (address != null) {
      final status = File('${dev.parent.path}/setup-status.txt');
      app.addListener(() => status.writeAsStringSync('${app.setupPhase.name} | ${app.setupLabel} | ${app.setupError ?? ''} | engine=${app.engineState.name}'));
    }
  }
  unawaited(app.ensureData(address: address));
  if (dev != null) {
    // Side-load diagnostics: what this build saw (read back with adb).
    try {
      File('${dev.parent.path}/status.json').writeAsStringSync(
          '{"dev":"${dev.path}","manifest":${File('${dev.path}/release/manifest.json').existsSync()},'
          '"flag":${File('${dev.path}/run-benchmark').existsSync()},"installError":${app.devInstallError == null ? 'null' : '"${app.devInstallError!.replaceAll('"', "'")}"'},'
          '"engine":"${app.engineState}","problem":${app.engineProblem == null ? 'null' : '"${app.engineProblem!.replaceAll('"', "'")}"'}}');
    } on Object catch (e) {
      debugPrint('SCRIPTURA_STATUS_FAILED $e');
    }
  }
  if (dev != null && File('${dev.path}/run-benchmark').existsSync()) await _deviceBenchmark(app, dev);
}

/// Side-loaded benchmark: when dev-packs/run-benchmark exists, time the engine on this device and write
/// dev-packs/benchmark.json (read it back with adb pull). Profiles that need ColBERT are skipped without the pack.
Future<void> _deviceBenchmark(AppController app, Directory dev) async {
  final out = <String, dynamic>{};
  final t = Stopwatch()..start();
  try {
    if (app.engineState != EngineState.ready) {
      out['error'] = app.engineProblem ?? 'engine not ready';
    } else {
      out['engine_ready_ms'] = t.elapsedMilliseconds;
      out['compass'] = await runBenchmark(app.search, profile: 'compass');
      out['lantern'] = await runBenchmark(app.search, profile: 'lantern');
    }
  } on Object catch (e) {
    out['error'] = '$e';
  }
  final text = benchmarkReport(out);
  debugPrint('SCRIPTURA_BENCHMARK $text');
  File('${dev.parent.path}/benchmark.json').writeAsStringSync(text);
}

class ScripturesReaderApp extends StatelessWidget {
  const ScripturesReaderApp({super.key, required this.app});
  final AppController app;

  @override
  Widget build(BuildContext context) {
    // The app theme is a saved preference; until the library is ready the welcome screen uses the Scriptura look.
    return ListenableBuilder(
      listenable: app,
      builder: (context, _) => ListenableBuilder(
        listenable: app.repository == null ? app : app.user, // the store is replaced when the library loads
        builder: (context, _) {
          final style = app.repository == null ? AppStyle.scriptura : AppStyle.parse(app.user.pref('app_theme'));
          return MaterialApp(
            title: 'Scriptura',
            debugShowCheckedModeBanner: false,
            theme: appTheme(Brightness.light, style),
            darkTheme: appTheme(Brightness.dark, style),
            themeMode: style.mode,
            home: ListenableBuilder(
              listenable: app,
              builder: (context, _) => app.repository == null ? WelcomeScreen(app: app) : AppShell(app: app),
            ),
          );
        },
      ),
    );
  }
}
