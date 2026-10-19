// Answer focus end to end with the real engine: device trial on first start, the offer, "Not now", downloading only
// the chosen pack from the bucket layout (served locally), and the engine reopening with it. Skipped when not built.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app_controller.dart';
import 'package:scriptures_reader_mobile/services/engine/answer_focus.dart';
import 'package:scriptures_reader_mobile/services/engine/search_models.dart';

import 'download_e2e_test.dart' show serve;

void main() {
  final bucket = Directory('../scriptura/artifacts/hosting/bucket');
  final lib = File('engine/target/release/scripture_engine.dll');
  final ready = File('${bucket.path}/answer-focus-int8-v1.zip').existsSync() && lib.existsSync() && Directory('generated-artifacts/engine-pack').existsSync();

  test('the trial chooses, the offer respects Not now, and only the chosen pack is fetched and used', skip: ready ? false : 'not built', () async {
    final server = await serve([bucket, Directory('../scriptura/artifacts/hosting/search-data')]);
    addTearDown(() => server.close(force: true));
    final root = Directory.systemTemp.createTempSync('scriptura-focus-');
    addTearDown(() => root.deleteSync(recursive: true));
    final app = AppController(
      root: root,
      environment: {'SCRIPTURA_ENGINE_LIB': lib.absolute.path, 'SCRIPTURA_ENGINE_PACK': Directory('generated-artifacts/engine-pack').absolute.path},
      devPacks: Directory('generated-artifacts').absolute,
    );
    await app.load();
    expect(app.engineState, EngineState.ready, reason: app.engineProblem);

    // the trial runs once the engine is ready (not holding it up), before anything is downloaded
    await app.focusTrial;
    // This fixture bucket's index.json lists only Ezra's answer-focus-* packs (no apollos-* entries), so pin the
    // preference to Ezra and re-measure; otherwise the default (Apollos) trial finds this dev machine fast enough
    // and the test's own ensureData() call below would ask the bucket for a pack it was never set up to serve.
    app.setFocusModelPreference(FocusModel.ezra);
    await app.remeasure();
    final choice = app.focusChoice!;
    expect(choice.variant, isNot(FocusVariant.none), reason: 'this development machine is fast enough');
    expect(app.focusInstalled, isFalse);

    final address = 'http://127.0.0.1:${server.port}/';
    await app.ensureData(address: address); // the small required packs; never Answer focus unasked
    expect(app.setupPhase, SetupPhase.idle, reason: app.setupError);
    expect(app.focusInstalled, isFalse);
    expect(app.offerAnswerFocus, isTrue);

    app.declineAnswerFocus();
    expect(app.offerAnswerFocus, isFalse, reason: 'Not now');

    await app.ensureData(address: address, includeFocus: true); // the reader asked (Settings)
    expect(app.setupPhase, SetupPhase.idle, reason: app.setupError);
    expect(app.focusInstalled, isTrue);
    expect(app.engineState, EngineState.ready, reason: app.engineProblem);
    final chosen = choice.variant == FocusVariant.fp16 ? 'answer-focus-fp16' : 'answer-focus-int8';
    final other = choice.variant == FocusVariant.fp16 ? 'answer-focus-int8' : 'answer-focus-fp16';
    expect(Directory('${root.path}/scriptura/$chosen').existsSync(), isTrue);
    expect(Directory('${root.path}/scriptura/$other').existsSync(), isFalse, reason: 'the other variant is never downloaded');

    final r = await app.search.search(SearchRequest.raw('focus', {'query': 'Why?', 'texts': ['Jesus wept.', 'And Seth begat Enos.']}));
    expect((r.raw['scores'] as List), hasLength(2));
    expect(r.raw['device'], choice.variant == FocusVariant.fp16 ? 'gpu' : 'cpu');

    // Off then On in quick succession: one engine at a time, and the last choice wins
    final off = app.setFocusMode(FocusMode.off);
    final on = app.setFocusMode(FocusMode.automatic);
    await Future.wait([off, on]);
    expect(app.engineState, EngineState.ready, reason: app.engineProblem);
    expect(app.search.hasFocus, isTrue, reason: 'the later restart (Automatic) must be the one left running');
    await app.close();
  }, timeout: const Timeout(Duration(minutes: 20)));
}
