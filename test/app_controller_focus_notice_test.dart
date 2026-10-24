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
}
