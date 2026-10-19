import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app_controller.dart';
import 'package:scriptures_reader_mobile/data/user/user_store.dart';
import 'package:scriptures_reader_mobile/services/engine/answer_focus.dart';
import 'package:scriptures_reader_mobile/services/engine/engine_pack.dart';
import 'package:scriptures_reader_mobile/services/engine/search_models.dart';

import 'fakes/fake_search_service.dart';

/// Writes a minimal (zero-file) install marker so [PackStore.active] reports this pack kind installed, without
/// any native engine or real pack content -- `measureDevice()`'s model-change and noise-protection logic only
/// needs to know a pack is present, never what's inside it.
void _markInstalled(Directory root, PackKind kind) {
  final dir = Directory('${root.path}/scriptura/${kind.dirName}')..createSync(recursive: true);
  File('${dir.path}/install.json').writeAsStringSync(jsonEncode({'format': kind.format, 'files': <String, dynamic>{}}));
}

void main() {
  (AppController, FakeSearchService) setup({bool gpu = true}) {
    final svc = FakeSearchService((r, id) async => SearchResponse(mode: 'device_trial', raw: {'cpu_ms': 1839.0, 'gpu': gpu && r.body?['probe_gpu'] != false}));
    return (AppController.fixed(search: svc, user: UserStore.memory()), svc);
  }

  test('a trial that never finished (a crashing graphics driver) skips the graphics probe next time', () async {
    final (app, svc) = setup();
    app.user.setPref('focus_trial_pending', '1');
    await app.measureDevice();
    expect(svc.requests.single.body!['probe_gpu'], false);
    expect(app.focusChoice!.variant, FocusVariant.int8);
    expect(app.user.pref('focus_trial_pending'), isNot('1'), reason: 'finished');
  });

  test('a normal trial probes the graphics chip and is marked pending while it runs', () async {
    final (app, svc) = setup();
    await app.measureDevice();
    expect(svc.requests.single.body!['probe_gpu'], isNot(false));
    expect(app.focusChoice!.variant, FocusVariant.fp16);
  });

  group('keep', () {
    const int8 = FocusChoice(FocusModel.ezra, FocusVariant.int8, 10, 1200);
    const fp16 = FocusChoice(FocusModel.ezra, FocusVariant.fp16, 10, 1200);

    test('an installed model is kept when a new trial would pick the other one', () {
      expect(keep(int8, fp16, installed: FocusVariant.int8), int8);
      expect(keep(int8, FocusChoice.none, installed: FocusVariant.int8), int8, reason: 'a busy machine does not orphan the pack');
    });

    test('with nothing installed the new trial decides', () {
      expect(keep(int8, fp16, installed: FocusVariant.none), fp16);
      expect(keep(null, int8, installed: FocusVariant.none), int8);
    });

    test('the same model takes the new measurement', () {
      const faster = FocusChoice(FocusModel.ezra, FocusVariant.int8, 30, 900);
      expect(keep(int8, faster, installed: FocusVariant.int8), faster);
    });
  });

  group('measureDevice change detection (Finding 1)', () {
    test('a pure model switch at the same variant is detected as changed (engine must restart)', () async {
      // Ezra fp16 -> Apollos fp16: same variant, different model. The device trial itself doesn't need to move;
      // a fresh preference change is enough to make resolveFallback hand back a different model.
      final svc = FakeSearchService((r, id) async => SearchResponse(mode: 'device_trial', raw: {'cpu_ms': 1839.0, 'gpu': true}));
      final app = AppController.fixed(search: svc, user: UserStore.memory());
      app.user.setPref('answer_focus_choice', const FocusChoice(FocusModel.ezra, FocusVariant.fp16, 10, 1200).toJson());
      app.setFocusModelPreference(FocusModel.apollos);
      final changed = await app.measureDevice();
      expect(app.focusChoice!.model, FocusModel.apollos);
      expect(app.focusChoice!.variant, FocusVariant.fp16); // same variant as before -- only the model moved
      expect(changed, isTrue, reason: 'a same-variant model switch must still trigger an engine restart');
    });

    test('adapt-only k/predictedMs step-downs (handled elsewhere) are not what measureDevice reports as a model change', () async {
      // Sanity companion: a trial that reproduces the exact same model+variant is NOT reported as changed, even
      // though a fresh FocusChoice (new k/predictedMs) was computed -- guards against reverting to `c != before`.
      final svc = FakeSearchService((r, id) async => SearchResponse(mode: 'device_trial', raw: {'cpu_ms': 1839.0, 'gpu': false}));
      final app = AppController.fixed(search: svc, user: UserStore.memory());
      app.user.setPref('answer_focus_choice', const FocusChoice(FocusModel.ezra, FocusVariant.int8, 10, 1269.0).toJson());
      final changed = await app.measureDevice();
      expect(app.focusChoice!.model, FocusModel.ezra);
      expect(app.focusChoice!.variant, FocusVariant.int8);
      expect(changed, isFalse);
    });
  });

  group('measureDevice composes keep() on resolveFallback() (Finding 2)', () {
    test('an installed Ezra int8 pack is not orphaned by a single noisy trial landing on fp16', () async {
      final root = Directory.systemTemp.createTempSync('scriptura-measure-');
      addTearDown(() => root.deleteSync(recursive: true));
      _markInstalled(root, PackKind.focusInt8);
      final svc = FakeSearchService((r, id) async => SearchResponse(mode: 'device_trial', raw: {'cpu_ms': 1839.0, 'gpu': true}));
      final app = AppController.fixed(root: root, search: svc, user: UserStore.memory())..setFocusModelPreference(FocusModel.ezra);
      app.user.setPref('answer_focus_choice', const FocusChoice(FocusModel.ezra, FocusVariant.int8, 10, 1200).toJson());
      await app.measureDevice();
      expect(app.focusChoice!.variant, FocusVariant.int8, reason: "keep()'s noise protection must still apply after resolveFallback");
      expect(app.focusChoice!.model, FocusModel.ezra);
    });

    test('an installed Apollos fp16 pack is not orphaned by a noisy trial landing on Apollos int8 (variant-level noise '
        'that resolveFallback alone does not catch, since the model itself did not change)', () async {
      final root = Directory.systemTemp.createTempSync('scriptura-measure-');
      addTearDown(() => root.deleteSync(recursive: true));
      _markInstalled(root, PackKind.apollosFp16);
      // gpu: false this run (a flaky driver) -> choose() still picks Apollos (preference + fits its CPU ladder), but
      // int8, not the installed fp16. resolveFallback's model-level check lets this through unchanged (same model,
      // "genuinely available now"); only keep()'s variant-level protection should stop the flip here.
      final svc = FakeSearchService((r, id) async => SearchResponse(mode: 'device_trial', raw: {'cpu_ms': 600.0, 'gpu': false}));
      final app = AppController.fixed(root: root, search: svc, user: UserStore.memory())..setFocusModelPreference(FocusModel.apollos);
      app.user.setPref('answer_focus_choice', const FocusChoice(FocusModel.apollos, FocusVariant.fp16, 10, 800).toJson());
      await app.measureDevice();
      expect(app.focusChoice!.model, FocusModel.apollos);
      expect(app.focusChoice!.variant, FocusVariant.fp16,
          reason: "keep()'s noise protection must still apply within Apollos, composed on top of resolveFallback");
    });
  });
}
