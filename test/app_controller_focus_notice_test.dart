// Pref round-trip for the Apollos-override-accepted flag: no engine, no filesystem.
import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app_controller.dart';
import 'package:scriptures_reader_mobile/services/engine/answer_focus.dart';

void main() {
  test('accepting the Apollos override is persisted', () {
    final controller = AppController.fixed();
    expect(controller.apollosOverrideAccepted, isFalse);
    controller.acceptApollosOverride();
    expect(controller.apollosOverrideAccepted, isTrue);
  });

  test('switching back to Ezra clears a previously accepted override', () {
    final controller = AppController.fixed();
    controller.acceptApollosOverride();
    expect(controller.apollosOverrideAccepted, isTrue);
    controller.setFocusModelPreference(FocusModel.ezra);
    expect(controller.apollosOverrideAccepted, isFalse);
  });

  test('a detour through Priscilla still clears a previously accepted Apollos override, '
      'so switching back to Apollos re-warns', () {
    final controller = AppController.fixed();
    controller.acceptApollosOverride();
    expect(controller.apollosOverrideAccepted, isTrue);
    controller.setFocusModelPreference(FocusModel.priscilla);
    expect(controller.apollosOverrideAccepted, isFalse, reason: 'a fresh Apollos pick after this detour must re-warn');
  });
}
