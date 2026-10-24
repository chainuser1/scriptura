// Pref round-trip for the model-generic override-accepted flag, plus the fresh-install default-setup notice
// (offerPriscillaDefaultSetup, which needs a real root directory to check installed-pack state): no engine.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app_controller.dart';
import 'package:scriptures_reader_mobile/data/user/user_store.dart';
import 'package:scriptures_reader_mobile/services/engine/answer_focus.dart';
import 'package:scriptures_reader_mobile/services/engine/engine_pack.dart';
import 'package:scriptures_reader_mobile/services/engine/search_models.dart';

import 'fakes/fake_search_service.dart';
import 'fakes/recording_install_controller.dart';

/// Writes a minimal (zero-file) install marker so [PackStore.active] reports this pack kind installed, without
/// any native engine or real pack content (same helper test/answer_focus_trial_test.dart defines).
void _markInstalled(Directory root, PackKind kind) {
  final dir = Directory('${root.path}/scriptura/${kind.dirName}')..createSync(recursive: true);
  File('${dir.path}/install.json').writeAsStringSync(jsonEncode({'format': kind.format, 'files': <String, dynamic>{}}));
}

void _markContentInstalled(Directory root) {
  final dir = Directory('${root.path}/scriptura/content/mini')..createSync(recursive: true);
  File('test/fixtures/content_v2_mini.db').copySync('${dir.path}/content.db');
  File('test/fixtures/catalog_mini.db').copySync('${dir.path}/catalog.db');
  File('${root.path}/scriptura/active.json').writeAsStringSync(jsonEncode({
    'release': 'mini',
    'files': {for (final name in ['content.db', 'catalog.db']) name: {'bytes': File('${dir.path}/$name').lengthSync()}},
  }));
}

void main() {
  group('automatic default lifecycle', () {
    test('slow fresh trial explains the fallback once without forcing another trial', () async {
      final root = Directory.systemTemp.createTempSync();
      addTearDown(() => root.deleteSync(recursive: true));
      final path = '${root.path}/user.db';
      final user = UserStore.open(path, contract: '');
      final svc = FakeSearchService((r, id) async =>
          SearchResponse(mode: 'device_trial', raw: {'cpu_ms': 40000, 'gpu': true}));
      final app = AppController.fixed(root: root, user: user, search: svc);
      expect(app.focusFellBackFromDefault, isFalse);
      await app.measureDevice();
      expect(app.focusFellBackFromDefault, isTrue);
      expect(app.focusTrialPreference, FocusModel.priscilla);
      expect(app.focusModelPreference, FocusModel.ezra);
      expect(app.focusTrialDue, isFalse);
      expect(app.offerPriscillaDefaultSetup, isFalse);
      _markInstalled(root, PackKind.focusFp16);
      expect(app.focusModelPreference, FocusModel.ezra);
      app.acknowledgeFocusFallback();
      expect(app.focusFellBackFromDefault, isFalse);
      expect(app.overrideAccepted(FocusModel.priscilla), isFalse);
      expect(svc.requests, hasLength(1));
      user.dispose();
      final reopened = UserStore.open(path, contract: '');
      addTearDown(reopened.dispose);
      final restarted = AppController.fixed(root: root, user: reopened);
      expect(restarted.focusModelPreference, FocusModel.ezra);
      expect(restarted.focusTrialDue, isFalse);
      expect(restarted.focusFellBackFromDefault, isFalse);
    });

    test('fast fresh trial survives Priscilla installation and restart', () async {
      final root = Directory.systemTemp.createTempSync();
      addTearDown(() => root.deleteSync(recursive: true));
      final path = '${root.path}/user.db';
      final user = UserStore.open(path, contract: '');
      final response = Completer<SearchResponse>();
      final app = AppController.fixed(root: root, user: user,
          search: FakeSearchService((r, id) => response.future));
      final trial = app.measureDevice();
      _markInstalled(root, PackKind.priscillaInt8);
      response.complete(SearchResponse(mode: 'device_trial', raw: {'cpu_ms': 200, 'gpu': false}));
      await trial;
      expect(app.focusChoice!.model, FocusModel.priscilla);
      expect(app.focusModelPreference, FocusModel.priscilla);
      expect(app.focusTrialPreference, FocusModel.priscilla);
      expect(app.focusTrialDue, isFalse);
      expect(app.focusFellBackFromDefault, isFalse);
      user.dispose();
      final reopened = UserStore.open(path, contract: '');
      addTearDown(reopened.dispose);
      final restarted = AppController.fixed(root: root, user: reopened);
      expect(restarted.focusModelPreference, FocusModel.priscilla);
      expect(restarted.focusTrialDue, isFalse);
    });

    test('Continue preserves the default before the trial starts', () async {
      final root = Directory.systemTemp.createTempSync();
      addTearDown(() => root.deleteSync(recursive: true));
      final app = RecordingInstallController(root: root, user: UserStore.memory(),
          search: FakeSearchService((r, id) async =>
              SearchResponse(mode: 'device_trial', raw: {'cpu_ms': 200, 'gpu': false})));
      _markContentInstalled(root);
      for (final kind in [PackKind.engine, PackKind.entities, PackKind.answers]) {
        _markInstalled(root, kind);
      }
      expect(app.missingData.difference({'colbert'}), isEmpty);
      await app.ensureData(includeFocus: true);
      _markInstalled(root, PackKind.priscillaInt8);
      await app.measureDevice();
      expect(app.focusModelPreference, FocusModel.priscilla);
      expect(app.focusChoice!.model, FocusModel.priscilla);
    });

    test('Continue intent survives content opening a disk UserStore and restart', () async {
      final root = Directory.systemTemp.createTempSync();
      addTearDown(() => root.deleteSync(recursive: true));
      final app = RecordingInstallController(root: root, user: UserStore.memory());
      await app.ensureData(includeFocus: true);
      _markContentInstalled(root);
      _markInstalled(root, PackKind.priscillaInt8);
      await app.load();
      expect(app.repository, isNotNull);
      expect(app.focusModelPreference, FocusModel.priscilla);
      expect(app.user.pref('focus_model_preference'), isNull);
      await app.close();
      final restarted = AppController(root: root, environment: const {});
      await restarted.load();
      expect(restarted.focusModelPreference, FocusModel.priscilla);
      await restarted.close();
    });

    test('disk explicit preference wins over temporary fresh-install intent', () async {
      final root = Directory.systemTemp.createTempSync();
      addTearDown(() => root.deleteSync(recursive: true));
      final app = RecordingInstallController(root: root, user: UserStore.memory());
      await app.ensureData(includeFocus: true);
      _markContentInstalled(root);
      final saved = UserStore.open('${root.path}/scriptura/user.db', contract: '');
      saved.setPref('focus_model_preference', 'aquila');
      saved.dispose();
      await app.load();
      expect(app.focusModelPreference, FocusModel.aquila);
      expect(app.focusFellBackFromDefault, isFalse);
      await app.close();
    });

    test('completed fallback and acknowledgement survive UserStore replacement', () async {
      final root = Directory.systemTemp.createTempSync();
      addTearDown(() => root.deleteSync(recursive: true));
      final app = AppController.fixed(root: root, search: FakeSearchService((r, id) async =>
          SearchResponse(mode: 'device_trial', raw: {'cpu_ms': 40000, 'gpu': false})));
      await app.measureDevice();
      app.acknowledgeFocusFallback();
      _markContentInstalled(root);
      await app.load();
      expect(app.focusChoice, FocusChoice.none);
      expect(app.focusModelPreference, FocusModel.ezra);
      expect(app.focusTrialPreference, FocusModel.priscilla);
      expect(app.focusTrialDue, isFalse);
      expect(app.focusFellBackFromDefault, isFalse);
      await app.close();
    });

    test('a running trial writes its captured preference to the replacement UserStore', () async {
      final root = Directory.systemTemp.createTempSync();
      addTearDown(() => root.deleteSync(recursive: true));
      final response = Completer<SearchResponse>();
      final app = AppController.fixed(root: root, search: FakeSearchService((r, id) => response.future));
      final trial = app.measureDevice();
      _markContentInstalled(root);
      _markInstalled(root, PackKind.priscillaInt8);
      await app.load();
      response.complete(SearchResponse(mode: 'device_trial', raw: {'cpu_ms': 200, 'gpu': false}));
      await trial;
      expect(app.focusChoice!.model, FocusModel.priscilla);
      expect(app.focusTrialPreference, FocusModel.priscilla);
      expect(app.focusTrialDue, isFalse);
      await app.close();
    });

    test('turning Off while a trial runs discards its result and warning', () async {
      final response = Completer<SearchResponse>();
      final app = AppController.fixed(search: FakeSearchService((r, id) => response.future));
      final trial = app.measureDevice();
      await app.setFocusMode(FocusMode.off);
      response.complete(SearchResponse(mode: 'device_trial', raw: {'cpu_ms': 40000, 'gpu': true}));
      await trial;
      expect(app.focusChoice, isNull);
      expect(app.focusFellBackFromDefault, isFalse);
    });

    test('runtime adaptation after a fitting trial is not a trial fallback notice', () async {
      final app = AppController.fixed(search: FakeSearchService((r, id) async =>
          SearchResponse(mode: 'device_trial', raw: {'cpu_ms': 200, 'gpu': false})));
      await app.measureDevice();
      for (var i = 0; i < 9; i++) {
        app.recordFocusTime(100000);
      }
      expect(app.focusChoice, FocusChoice.none);
      expect(app.focusFellBackFromDefault, isFalse);
    });

    test('an explicit pick during the trial is preserved', () async {
      final response = Completer<SearchResponse>();
      final app = AppController.fixed(search: FakeSearchService((r, id) => response.future));
      final trial = app.measureDevice();
      app.setFocusModelPreference(FocusModel.aquila);
      response.complete(SearchResponse(mode: 'device_trial', raw: {'cpu_ms': 200, 'gpu': false}));
      await trial;
      expect(app.focusModelPreference, FocusModel.aquila);
      expect(app.focusChoice, isNull);
      expect(app.focusTrialDue, isTrue);
      expect(app.focusFellBackFromDefault, isFalse);
    });

    test('explicit preferences, Off and failed trials do not produce a default warning', () async {
      for (final scenario in ['explicit', 'off', 'failed']) {
        final app = AppController.fixed(search: FakeSearchService((r, id) async {
          if (scenario == 'failed') throw StateError('trial failed');
          return SearchResponse(mode: 'device_trial', raw: {'cpu_ms': 40000, 'gpu': false});
        }));
        if (scenario == 'explicit') app.setFocusModelPreference(FocusModel.priscilla);
        if (scenario == 'off') app.user.setPref('answer_focus', 'off');
        await app.measureDevice();
        expect(app.focusFellBackFromDefault, isFalse, reason: scenario);
      }
    });
  });

  test('ensureData requests the preferred model pack before any trial has run', () async {
    final root = Directory.systemTemp.createTempSync();
    addTearDown(() => root.deleteSync(recursive: true));
    final controller = RecordingInstallController(root: root, user: UserStore.memory());

    expect(controller.focusChoice, isNull);
    expect(controller.focusModelPreference, FocusModel.priscilla);
    await controller.ensureData(includeFocus: true);

    expect(controller.requestedKinds, contains('priscilla-int8'));
  });

  for (final entry in {
    FocusModel.apollos: 'apollos-int8',
    FocusModel.aquila: 'aquila-int8',
  }.entries) {
    test('ensureData requests ${entry.key.name} int8 before any trial has run', () async {
      final root = Directory.systemTemp.createTempSync();
      addTearDown(() => root.deleteSync(recursive: true));
      final controller = RecordingInstallController(root: root, user: UserStore.memory())..setFocusModelPreference(entry.key);

      await controller.ensureData(includeFocus: true);

      expect(controller.requestedKinds, contains(entry.value));
    });
  }

  test('ensureData does not request an already-installed preferred model again', () async {
    final root = Directory.systemTemp.createTempSync();
    addTearDown(() => root.deleteSync(recursive: true));
    _markInstalled(root, PackKind.priscillaInt8);
    final controller = RecordingInstallController(root: root, user: UserStore.memory())..setFocusModelPreference(FocusModel.priscilla);

    await controller.ensureData(includeFocus: true);

    expect(controller.requestedKinds, isNot(contains('priscilla-int8')));
  });

  test('ensureData honors a completed trial that chose no focus model', () async {
    final root = Directory.systemTemp.createTempSync();
    addTearDown(() => root.deleteSync(recursive: true));
    final controller = RecordingInstallController(root: root, user: UserStore.memory());
    controller.user.setPref(
      'answer_focus_choice',
      const FocusChoice(FocusModel.priscilla, FocusVariant.none, 0, 200).toJson(),
    );

    await controller.ensureData(includeFocus: true);

    expect(controller.requestedKinds, isNot(contains('priscilla-int8')));
  });

  test('ensureData does not request the preferred model before a trial while Answer focus is off', () async {
    final root = Directory.systemTemp.createTempSync();
    addTearDown(() => root.deleteSync(recursive: true));
    final controller = RecordingInstallController(root: root, user: UserStore.memory());
    controller.user.setPref('answer_focus', 'off');

    await controller.ensureData(includeFocus: true);

    expect(controller.requestedKinds, isNot(contains('priscilla-int8')));
  });

  test('ensureData does not request a persisted trial choice while Answer focus is off', () async {
    final root = Directory.systemTemp.createTempSync();
    addTearDown(() => root.deleteSync(recursive: true));
    final controller = RecordingInstallController(root: root, user: UserStore.memory());
    controller.user.setPref(
      'answer_focus_choice',
      const FocusChoice(FocusModel.apollos, FocusVariant.int8, 10, 200).toJson(),
    );
    controller.user.setPref('answer_focus', 'off');

    await controller.ensureData(includeFocus: true);

    expect(controller.requestedKinds, isNot(contains('apollos-int8')));
  });

  test('accepting the Apollos override is persisted', () {
    final controller = AppController.fixed();
    expect(controller.overrideAccepted(FocusModel.apollos), isFalse);
    controller.acceptOverride(FocusModel.apollos);
    expect(controller.overrideAccepted(FocusModel.apollos), isTrue);
  });

  test(
      'an Apollos override accepted under the old, pre-generalization pref key still reads as accepted '
      '(a real shipped release may have readers with this key already set)', () {
    final controller = AppController.fixed();
    controller.user.setPref('apollos_override_accepted', '1');
    expect(controller.overrideAccepted(FocusModel.apollos), isTrue);
  });

  test('accepting the Priscilla override is persisted', () {
    final controller = AppController.fixed();
    expect(controller.overrideAccepted(FocusModel.priscilla), isFalse);
    controller.acceptOverride(FocusModel.priscilla);
    expect(controller.overrideAccepted(FocusModel.priscilla), isTrue);
  });

  test('switching back to Ezra clears a previously accepted Apollos override', () {
    final controller = AppController.fixed();
    controller.acceptOverride(FocusModel.apollos);
    expect(controller.overrideAccepted(FocusModel.apollos), isTrue);
    controller.setFocusModelPreference(FocusModel.ezra);
    expect(controller.overrideAccepted(FocusModel.apollos), isFalse);
  });

  test('switching back to Ezra clears a previously accepted Priscilla override', () {
    final controller = AppController.fixed();
    controller.acceptOverride(FocusModel.priscilla);
    expect(controller.overrideAccepted(FocusModel.priscilla), isTrue);
    controller.setFocusModelPreference(FocusModel.ezra);
    expect(controller.overrideAccepted(FocusModel.priscilla), isFalse);
  });

  test(
      'a detour through Priscilla still clears a previously accepted Apollos override, '
      'so switching back to Apollos re-warns', () {
    final controller = AppController.fixed();
    controller.acceptOverride(FocusModel.apollos);
    expect(controller.overrideAccepted(FocusModel.apollos), isTrue);
    controller.setFocusModelPreference(FocusModel.priscilla);
    expect(controller.overrideAccepted(FocusModel.apollos), isFalse, reason: 'a fresh Apollos pick after this detour must re-warn');
  });

  test(
      'a detour through Apollos still clears a previously accepted Priscilla override, '
      'so switching back to Priscilla re-warns', () {
    final controller = AppController.fixed();
    controller.acceptOverride(FocusModel.priscilla);
    expect(controller.overrideAccepted(FocusModel.priscilla), isTrue);
    controller.setFocusModelPreference(FocusModel.apollos);
    expect(controller.overrideAccepted(FocusModel.priscilla), isFalse, reason: 'a fresh Priscilla pick after this detour must re-warn');
  });

  test('accepting the Apollos override does not also suppress Priscilla\'s own warning', () {
    final controller = AppController.fixed();
    controller.acceptOverride(FocusModel.apollos);
    expect(controller.overrideAccepted(FocusModel.apollos), isTrue);
    expect(controller.overrideAccepted(FocusModel.priscilla), isFalse);
  });

  test('accepting the Priscilla override does not also suppress Apollos\'s own warning', () {
    final controller = AppController.fixed();
    controller.acceptOverride(FocusModel.priscilla);
    expect(controller.overrideAccepted(FocusModel.priscilla), isTrue);
    expect(controller.overrideAccepted(FocusModel.apollos), isFalse);
  });

  test('accepting the Apollos override does not also suppress Aquila\'s own warning', () {
    final controller = AppController.fixed();
    controller.acceptOverride(FocusModel.apollos);
    expect(controller.overrideAccepted(FocusModel.apollos), isTrue);
    expect(controller.overrideAccepted(FocusModel.aquila), isFalse);
  });

  test('accepting the Aquila override does not also suppress Apollos\'s or Priscilla\'s own warning', () {
    final controller = AppController.fixed();
    controller.acceptOverride(FocusModel.aquila);
    expect(controller.overrideAccepted(FocusModel.aquila), isTrue);
    expect(controller.overrideAccepted(FocusModel.apollos), isFalse);
    expect(controller.overrideAccepted(FocusModel.priscilla), isFalse);
  });

  test(
      'a detour through Aquila still clears a previously accepted Priscilla override, '
      'so switching back to Priscilla re-warns', () {
    final controller = AppController.fixed();
    controller.acceptOverride(FocusModel.priscilla);
    expect(controller.overrideAccepted(FocusModel.priscilla), isTrue);
    controller.setFocusModelPreference(FocusModel.aquila);
    expect(controller.overrideAccepted(FocusModel.priscilla), isFalse);
  });

  test(
      'a detour through Aquila clears an Apollos override accepted under the legacy, pre-generalization key too '
      '(a real shipped reader may only have that key set, never the per-model one)', () {
    final controller = AppController.fixed();
    controller.user.setPref('apollos_override_accepted', '1');
    expect(controller.overrideAccepted(FocusModel.apollos), isTrue);
    controller.setFocusModelPreference(FocusModel.aquila);
    expect(controller.overrideAccepted(FocusModel.apollos), isFalse,
        reason: 'a fresh Apollos pick after this detour must re-warn, even for a legacy-key reader');
  });

  test('with no preference ever set, the default Answer focus model is Priscilla, not Ezra', () {
    final controller = AppController.fixed();
    expect(controller.user.pref('focus_model_preference'), isNull);
    expect(controller.focusModelPreference, FocusModel.priscilla);
  });

  test('with nothing installed and no preference ever set, the default is still Priscilla', () {
    final root = Directory.systemTemp.createTempSync();
    addTearDown(() => root.deleteSync(recursive: true));
    final controller = AppController.fixed(root: root, user: UserStore.memory());
    expect(controller.focusModelPreference, FocusModel.priscilla);
  });

  test('with Ezra already installed and no preference ever set, the default stays Ezra, not Priscilla', () {
    final root = Directory.systemTemp.createTempSync();
    addTearDown(() => root.deleteSync(recursive: true));
    _markInstalled(root, PackKind.focusInt8);
    final controller = AppController.fixed(root: root, user: UserStore.memory());
    expect(controller.focusModelPreference, FocusModel.ezra);
  });

  test('with Apollos already installed (not Priscilla) and no preference ever set, the default stays Ezra', () {
    final root = Directory.systemTemp.createTempSync();
    addTearDown(() => root.deleteSync(recursive: true));
    _markInstalled(root, PackKind.apollosInt8);
    final controller = AppController.fixed(root: root, user: UserStore.memory());
    expect(controller.focusModelPreference, FocusModel.ezra);
  });

  test('an installed Ezra upgrade with a persisted Ezra trial does not become due when the preference is unset', () {
    final root = Directory.systemTemp.createTempSync();
    addTearDown(() => root.deleteSync(recursive: true));
    _markInstalled(root, PackKind.focusInt8);
    final controller = AppController.fixed(root: root, user: UserStore.memory());
    controller.user.setPref('answer_focus_choice', const FocusChoice(FocusModel.ezra, FocusVariant.int8, 10, 1200).toJson());
    controller.user.setPref('focus_trial_preference', 'ezra');

    expect(controller.user.pref('focus_model_preference'), isNull);
    expect(controller.focusModelPreference, FocusModel.ezra);
    expect(controller.focusTrialDue, isFalse);
    expect(controller.offerPriscillaDefaultSetup, isFalse);
    expect(controller.focusFellBackFromDefault, isFalse);
  });

  test('an explicit Ezra pick is remembered and never silently moved to Priscilla', () {
    final controller = AppController.fixed();
    controller.setFocusModelPreference(FocusModel.ezra);
    expect(controller.focusModelPreference, FocusModel.ezra);
  });

  test('offerPriscillaDefaultSetup is true when no model has ever been chosen and nothing is installed', () {
    final root = Directory.systemTemp.createTempSync();
    addTearDown(() => root.deleteSync(recursive: true));
    final controller = AppController.fixed(root: root, user: UserStore.memory());
    expect(controller.offerPriscillaDefaultSetup, isTrue);
  });

  test('offerPriscillaDefaultSetup is false once the reader has explicitly chosen a model', () {
    final root = Directory.systemTemp.createTempSync();
    addTearDown(() => root.deleteSync(recursive: true));
    final controller = AppController.fixed(root: root, user: UserStore.memory());
    controller.setFocusModelPreference(FocusModel.ezra);
    expect(controller.offerPriscillaDefaultSetup, isFalse);
  });

  test('offerPriscillaDefaultSetup is false after the reader dismisses it, even though the pref is still unset', () {
    final root = Directory.systemTemp.createTempSync();
    addTearDown(() => root.deleteSync(recursive: true));
    final controller = AppController.fixed(root: root, user: UserStore.memory());
    controller.declineAnswerFocus(); // existing one-shot dismiss, reused rather than a new pref
    expect(controller.offerPriscillaDefaultSetup, isFalse);
  });

  test('offerPriscillaDefaultSetup is false once Priscilla is actually installed, even with the pref still unset', () {
    final root = Directory.systemTemp.createTempSync();
    addTearDown(() => root.deleteSync(recursive: true));
    _markInstalled(root, PackKind.priscillaInt8);
    final controller = AppController.fixed(root: root, user: UserStore.memory());
    expect(controller.offerPriscillaDefaultSetup, isFalse);
  });

  test('offerPriscillaDefaultSetup is false once any model is installed', () {
    final root = Directory.systemTemp.createTempSync();
    addTearDown(() => root.deleteSync(recursive: true));
    _markInstalled(root, PackKind.apollosInt8);
    final controller = AppController.fixed(root: root, user: UserStore.memory());
    expect(controller.offerPriscillaDefaultSetup, isFalse);
  });

  test('offerPriscillaDefaultSetup is false while Answer focus is off', () {
    final root = Directory.systemTemp.createTempSync();
    addTearDown(() => root.deleteSync(recursive: true));
    final controller = AppController.fixed(root: root, user: UserStore.memory());
    controller.user.setPref('answer_focus', 'off');
    expect(controller.offerPriscillaDefaultSetup, isFalse);
  });

  test('offerPriscillaDefaultSetup is false after a completed trial chose no focus model', () {
    final root = Directory.systemTemp.createTempSync();
    addTearDown(() => root.deleteSync(recursive: true));
    final controller = AppController.fixed(root: root, user: UserStore.memory());
    controller.user.setPref(
      'answer_focus_choice',
      const FocusChoice(FocusModel.priscilla, FocusVariant.none, 0, 200).toJson(),
    );
    expect(controller.offerPriscillaDefaultSetup, isFalse);
  });
}
