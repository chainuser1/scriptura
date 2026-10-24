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
      // Ezra int8 k=30 -> Apollos int8 k=30: same variant, different model. A fast-enough device (200ms, same
      // speed used elsewhere to keep both ladders comfortably under budget -- Apollos's fp16/GPU tier is gated
      // off for now, so this has to go through its own CPU ladder, same as any other Apollos choice today) is
      // enough for a fresh preference change to make resolveFallback hand back a different model.
      final svc = FakeSearchService((r, id) async => SearchResponse(mode: 'device_trial', raw: {'cpu_ms': 200.0, 'gpu': true}));
      final app = AppController.fixed(search: svc, user: UserStore.memory());
      app.user.setPref('answer_focus_choice', const FocusChoice(FocusModel.ezra, FocusVariant.int8, 30, 414.0).toJson());
      app.setFocusModelPreference(FocusModel.apollos);
      final changed = await app.measureDevice();
      expect(app.focusChoice!.model, FocusModel.apollos);
      expect(app.focusChoice!.variant, FocusVariant.int8); // same variant as before -- only the model moved
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

    test('an installed Priscilla int8 pack is not orphaned when preferred and its own ladder still fits '
        '(keep()\'s variant-level noise protection, exercised for Apollos\'s own int8/fp16 split above, has '
        'nothing to protect for Priscilla: it has no fp16 tier, so every fitting trial already lands on int8 '
        'regardless -- this test instead confirms resolveFallback correctly keeps the installed pack\'s model '
        'selected through measureDevice\'s real composition, not a synthetic keep() scenario that cannot occur)', () async {
      final root = Directory.systemTemp.createTempSync('scriptura-priscilla-');
      addTearDown(() => root.deleteSync(recursive: true));
      _markInstalled(root, PackKind.priscillaInt8);
      final svc = FakeSearchService((r, id) async => SearchResponse(mode: 'device_trial', raw: {'cpu_ms': 1839.0, 'gpu': true}));
      final app = AppController.fixed(root: root, search: svc, user: UserStore.memory())..setFocusModelPreference(FocusModel.priscilla);
      app.user.setPref('answer_focus_choice', const FocusChoice(FocusModel.priscilla, FocusVariant.int8, 10, 600).toJson());
      await app.measureDevice();
      expect(app.focusChoice!.model, FocusModel.priscilla);
      expect(app.focusChoice!.variant, FocusVariant.int8);
    });

    test('an installed Aquila int8 pack is not orphaned when preferred and its own ladder still fits', () async {
      final root = Directory.systemTemp.createTempSync('scriptura-aquila-');
      addTearDown(() => root.deleteSync(recursive: true));
      _markInstalled(root, PackKind.aquilaInt8);
      final svc = FakeSearchService((r, id) async => SearchResponse(mode: 'device_trial', raw: {'cpu_ms': 200.0, 'gpu': true}));
      final app = AppController.fixed(root: root, search: svc, user: UserStore.memory())..setFocusModelPreference(FocusModel.aquila);
      app.user.setPref('answer_focus_choice', const FocusChoice(FocusModel.aquila, FocusVariant.int8, 10, 600).toJson());
      await app.measureDevice();
      expect(app.focusChoice!.model, FocusModel.aquila);
      expect(app.focusChoice!.variant, FocusVariant.int8);
    });

    test('a chosen but never-downloaded Apollos does not block the Ezra fallback once Apollos stops fitting', () async {
      // Apollos's 40s budget is generous, so this needs a genuinely very slow device (cpuMs=4200): Apollos's own
      // ladder exceeds 40000ms even at k=10 (measured _apollosCpuFactor ~14x Ezra's), and Ezra's own 1500ms
      // budget fails too at every k under Automatic -- mode On keeps Ezra at k=10 anyway, which is what
      // surfaces "falls back to Ezra" here rather than FocusVariant.none. An explicit Apollos preference
      // (Ezra is the default now) so resolveFallback's Apollos path is actually exercised.
      final root = Directory.systemTemp.createTempSync('scriptura-measure-');
      addTearDown(() => root.deleteSync(recursive: true));
      final svc = FakeSearchService((r, id) async => SearchResponse(mode: 'device_trial', raw: {'cpu_ms': 4200.0, 'gpu': false}));
      final app = AppController.fixed(root: root, search: svc, user: UserStore.memory())..setFocusModelPreference(FocusModel.apollos);
      app.user.setPref('answer_focus', 'on');
      app.user.setPref('answer_focus_choice', const FocusChoice(FocusModel.apollos, FocusVariant.fp16, 10, 800).toJson());
      await app.measureDevice();
      expect(app.focusChoice!.model, FocusModel.ezra);

      // The same trial with the Apollos pack installed keeps it (noise protection for a real download).
      _markInstalled(root, PackKind.apollosFp16);
      app.user.setPref('answer_focus_choice', const FocusChoice(FocusModel.apollos, FocusVariant.fp16, 10, 800).toJson());
      await app.measureDevice();
      expect(app.focusChoice, const FocusChoice(FocusModel.apollos, FocusVariant.fp16, 10, 800));
    });
  });

  group('the trial is re-run when the preference it ran under is not the current one (C2)', () {
    test('an upgrading user with an old Ezra choice and no recorded trial preference is due a trial, and stays on Ezra', () async {
      // Ezra is the default preference -- no auto-migration to Apollos. An old Ezra choice from before this field
      // existed is still due a trial (so focusTrialPreference gets recorded), but correctly lands back on Ezra.
      final svc = FakeSearchService((r, id) async => SearchResponse(mode: 'device_trial', raw: {'cpu_ms': 200.0, 'gpu': r.body?['probe_gpu'] != false}));
      final app = AppController.fixed(search: svc, user: UserStore.memory());
      app.user.setPref('answer_focus_choice', const FocusChoice(FocusModel.ezra, FocusVariant.fp16, 10, 1200).toJson());
      expect(app.focusTrialPreference, isNull);
      expect(app.focusTrialDue, isTrue, reason: 'the Ezra choice was never evaluated under a recorded trial preference');
      await app.measureDevice();
      expect(app.focusChoice!.model, FocusModel.ezra, reason: 'Ezra is the default; no auto-migration to Apollos');
      expect(app.focusTrialPreference, FocusModel.ezra);
      expect(app.focusTrialDue, isFalse);
    });

    test('changing the preference without a finished trial leaves one due; a failed trial records nothing', () async {
      final svc = FakeSearchService((r, id) async => throw Exception('engine busy'));
      final app = AppController.fixed(search: svc, user: UserStore.memory());
      app.user.setPref('answer_focus_choice', const FocusChoice(FocusModel.ezra, FocusVariant.fp16, 10, 800).toJson());
      app.user.setPref('focus_trial_preference', 'ezra');
      expect(app.focusTrialDue, isFalse);
      app.setFocusModelPreference(FocusModel.apollos);
      expect(await app.measureDevice(), isFalse);
      expect(app.focusTrialPreference, FocusModel.ezra);
      expect(app.focusTrialDue, isTrue, reason: 'the next start re-trials under Apollos');
    });
  });
}
