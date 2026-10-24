// Pref round-trip for the model-generic override-accepted flag, plus the fresh-install default-setup notice
// (offerPriscillaDefaultSetup, which needs a real root directory to check installed-pack state): no engine.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app_controller.dart';
import 'package:scriptures_reader_mobile/data/user/user_store.dart';
import 'package:scriptures_reader_mobile/services/engine/answer_focus.dart';
import 'package:scriptures_reader_mobile/services/engine/engine_pack.dart';

/// Writes a minimal (zero-file) install marker so [PackStore.active] reports this pack kind installed, without
/// any native engine or real pack content (same helper test/answer_focus_trial_test.dart defines).
void _markInstalled(Directory root, PackKind kind) {
  final dir = Directory('${root.path}/scriptura/${kind.dirName}')..createSync(recursive: true);
  File('${dir.path}/install.json').writeAsStringSync(jsonEncode({'format': kind.format, 'files': <String, dynamic>{}}));
}

void main() {
  test('accepting the Apollos override is persisted', () {
    final controller = AppController.fixed();
    expect(controller.overrideAccepted(FocusModel.apollos), isFalse);
    controller.acceptOverride(FocusModel.apollos);
    expect(controller.overrideAccepted(FocusModel.apollos), isTrue);
  });

  test('an Apollos override accepted under the old, pre-generalization pref key still reads as accepted '
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

  test('a detour through Priscilla still clears a previously accepted Apollos override, '
      'so switching back to Apollos re-warns', () {
    final controller = AppController.fixed();
    controller.acceptOverride(FocusModel.apollos);
    expect(controller.overrideAccepted(FocusModel.apollos), isTrue);
    controller.setFocusModelPreference(FocusModel.priscilla);
    expect(controller.overrideAccepted(FocusModel.apollos), isFalse, reason: 'a fresh Apollos pick after this detour must re-warn');
  });

  test('a detour through Apollos still clears a previously accepted Priscilla override, '
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

  test('a detour through Aquila still clears a previously accepted Priscilla override, '
      'so switching back to Priscilla re-warns', () {
    final controller = AppController.fixed();
    controller.acceptOverride(FocusModel.priscilla);
    expect(controller.overrideAccepted(FocusModel.priscilla), isTrue);
    controller.setFocusModelPreference(FocusModel.aquila);
    expect(controller.overrideAccepted(FocusModel.priscilla), isFalse);
  });

  test('a detour through Aquila clears an Apollos override accepted under the legacy, pre-generalization key too '
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

  test('an explicit Ezra pick is remembered and never silently moved to Priscilla', () {
    final controller = AppController.fixed();
    controller.setFocusModelPreference(FocusModel.ezra);
    expect(controller.focusModelPreference, FocusModel.ezra);
  });

  test('offerPriscillaDefaultSetup is true when no model has ever been chosen and nothing is installed', () {
    final controller = AppController.fixed(root: Directory.systemTemp.createTempSync(), user: UserStore.memory());
    expect(controller.offerPriscillaDefaultSetup, isTrue);
  });

  test('offerPriscillaDefaultSetup is false once the reader has explicitly chosen a model', () {
    final controller = AppController.fixed(root: Directory.systemTemp.createTempSync(), user: UserStore.memory());
    controller.setFocusModelPreference(FocusModel.ezra);
    expect(controller.offerPriscillaDefaultSetup, isFalse);
  });

  test('offerPriscillaDefaultSetup is false after the reader dismisses it, even though the pref is still unset', () {
    final controller = AppController.fixed(root: Directory.systemTemp.createTempSync(), user: UserStore.memory());
    controller.declineAnswerFocus(); // existing one-shot dismiss, reused rather than a new pref
    expect(controller.offerPriscillaDefaultSetup, isFalse);
  });

  test('offerPriscillaDefaultSetup is false once Priscilla is actually installed, even with the pref still unset', () {
    final root = Directory.systemTemp.createTempSync();
    _markInstalled(root, PackKind.priscillaInt8);
    final controller = AppController.fixed(root: root, user: UserStore.memory());
    expect(controller.offerPriscillaDefaultSetup, isFalse);
  });
}
