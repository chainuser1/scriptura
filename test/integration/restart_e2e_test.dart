// Offline end to end through the real AppController: install the content release into an app data directory
// (hash-verified), start the engine, search, "restart" with a fresh controller on the same directory, search again.
// Skipped when the generated artifacts are absent. No network is touched.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app_controller.dart';
import 'package:scriptures_reader_mobile/services/engine/search_models.dart';

void main() {
  final lib = File('engine/target/release/scripture_engine.dll');
  final enginePack = Directory('generated-artifacts/engine-pack');
  final colbert = Directory('generated-artifacts/colbert-pack-v1');
  final release = Directory('generated-artifacts/release');
  final ready = lib.existsSync() && enginePack.existsSync() && release.existsSync();

  test('install, search, restart, search again', skip: ready ? false : 'artifacts not built', () async {
    final root = Directory.systemTemp.createTempSync('scriptura-e2e-');
    addTearDown(() => root.deleteSync(recursive: true));
    final env = {
      'SCRIPTURA_ENGINE_LIB': lib.absolute.path,
      'SCRIPTURA_ENGINE_PACK': enginePack.absolute.path,
      if (colbert.existsSync()) 'SCRIPTURA_COLBERT_PACK': colbert.absolute.path,
    };

    var app = AppController(root: root, environment: env);
    await app.load();
    expect(app.repository, isNull, reason: 'nothing installed yet');
    expect(app.engineState, EngineState.unavailable);

    await app.installRelease(release); // verifies size and SHA-256 of every file, then activates
    expect(app.repository, isNotNull);
    expect(app.engineState, EngineState.ready, reason: app.engineProblem);

    Future<void> exercise(AppController a) async {
      final repo = a.repository!;
      final s = await a.search.search(SearchRequest.search('What is faith?'));
      expect(s.hits, isNotEmpty);
      final p = repo.getPassage(s.hits.first.verseId);
      expect(p.text, isNotEmpty);

      final ref = await a.search.search(SearchRequest.search('Psalm 23:1'));
      expect(ref.mode, 'reference');
      expect(repo.getPassage(ref.reference!.firstVerseId!).reference, 'Psalms 23:1');

      final ph = await a.search.search(SearchRequest.phrase('the Lord is my shepherd'));
      expect(ph.hits.map((h) => h.verseId), contains(ref.reference!.firstVerseId));

      final sim = await a.search.search(SearchRequest.similar(ref.reference!.firstVerseId!, topK: 3));
      expect(sim.hits, hasLength(3));

      final es = await a.search.search(SearchRequest.phrase('en el principio', language: 'spanish'));
      expect(es.total, greaterThan(0));
    }

    await exercise(app);
    await app.close();

    // process restart: a brand-new controller on the same data directory finds everything installed
    app = AppController(root: root, environment: env);
    await app.load();
    expect(app.repository, isNotNull);
    expect(app.engineState, EngineState.ready, reason: app.engineProblem);
    await exercise(app);
    await app.close();
  }, timeout: const Timeout(Duration(minutes: 5)));
}
