// Model-aware pack/kind resolution: a persisted Apollos choice must resolve to the apollos-* pack kind, not the
// Ezra-named answer-focus-* kind (see app_controller.dart's focusKind / _focusPack()).
import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app_controller.dart';
import 'package:scriptures_reader_mobile/services/engine/answer_focus.dart';

void main() {
  test('a persisted Apollos fp16 choice resolves to the apollos-fp16 pack kind', () {
    final controller = AppController.fixed();
    controller.user.setPref('answer_focus_choice', const FocusChoice(FocusModel.apollos, FocusVariant.fp16, 10, 800).toJson());
    expect(controller.focusKind, 'apollos-fp16');
  });

  test('a persisted Apollos int8 choice resolves to the apollos-int8 pack kind', () {
    final controller = AppController.fixed();
    controller.user.setPref('answer_focus_choice', const FocusChoice(FocusModel.apollos, FocusVariant.int8, 30, 1200).toJson());
    expect(controller.focusKind, 'apollos-int8');
  });

  test('a persisted Ezra choice still resolves to the answer-focus-* kind', () {
    final controller = AppController.fixed();
    controller.user.setPref('answer_focus_choice', const FocusChoice(FocusModel.ezra, FocusVariant.int8, 10, 1200).toJson());
    expect(controller.focusKind, 'answer-focus-int8');
  });

  test('focusModelPreference defaults to Priscilla when no preference is persisted yet', () {
    final controller = AppController.fixed();
    expect(controller.focusModelPreference, FocusModel.priscilla);
  });

  test('setFocusModelPreference persists an explicit Ezra choice', () {
    final controller = AppController.fixed();
    controller.setFocusModelPreference(FocusModel.ezra);
    expect(controller.focusModelPreference, FocusModel.ezra);
  });
}
