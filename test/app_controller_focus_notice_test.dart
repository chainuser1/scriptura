// Pref round-trip for the model-generic override-accepted flag: no engine, no filesystem.
import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app_controller.dart';
import 'package:scriptures_reader_mobile/services/engine/answer_focus.dart';

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
}
