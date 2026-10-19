// Pref round-trip for the Apollos-unavailable notice flag: no engine, no filesystem.
import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app_controller.dart';

void main() {
  test('the Apollos-unavailable notice is shown once, then stays marked', () {
    final controller = AppController.fixed();
    expect(controller.apollosUnavailableNoticeShown, isFalse);
    controller.markApollosUnavailableNoticeShown();
    expect(controller.apollosUnavailableNoticeShown, isTrue);
  });
}
