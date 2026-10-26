import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app_controller.dart';
import 'package:scriptures_reader_mobile/data/user/user_store.dart';
import 'package:scriptures_reader_mobile/services/engine/answer_focus.dart';
import 'package:scriptures_reader_mobile/services/engine/search_models.dart';

import 'fakes/fake_search_service.dart';

void main() {
  test('limit survives a restart, model changes, remeasurement and Off', () async {
    final dir = Directory.systemTemp.createTempSync('scriptura-focus-limit-');
    addTearDown(() => dir.deleteSync(recursive: true));
    UserStore open() => UserStore.open('${dir.path}/user.db', contract: 'test');
    final first = AppController.fixed(user: open());
    expect(first.focusLimit, 60);
    first.setFocusLimit(15);
    first.dispose();
    final service = FakeSearchService((r, id) async => SearchResponse(
        mode: 'device_trial', raw: {'cpu_ms': 100, 'gpu': true}));
    final app = AppController.fixed(user: open(), search: service);
    addTearDown(app.dispose);
    expect(app.focusLimit, 15);
    for (final model in FocusModel.values) {
      app.setFocusModelPreference(model);
      await app.measureDevice();
      expect(app.focusChoice!.model, model);
      expect(app.focusChoice!.k, 15);
    }
    await app.setFocusMode(FocusMode.off);
    app.setFocusLimit(100);
    await app.setFocusMode(FocusMode.on);
    expect(app.focusChoice!.k, 100);
    expect(app.focusLimit, 100);
  });

  test('existing supported counts survive; legacy 80 and invalid prefs use 60', () {
    final app = AppController.fixed();
    addTearDown(app.dispose);
    for (final k in [10, 15, 30, 60, 100, 80, 0]) {
      app.user.setPref('answer_focus_choice', FocusChoice(FocusModel.priscilla, FocusVariant.int8, k, 100).toJson());
      expect(app.focusLimit, [80, 0].contains(k) ? 60 : k);
      expect(app.focusChoice!.k, app.focusLimit);
    }
    app.user.setPref('answer_focus_limit', 'invalid');
    expect(app.focusLimit, 60);
    expect(() => app.setFocusLimit(80), throwsArgumentError);
  });

  test('a limit change during a trial wins over the old saved choice', () async {
    final result = Completer<SearchResponse>();
    final app = AppController.fixed(search: FakeSearchService((r, id) => result.future));
    addTearDown(app.dispose);
    app.setFocusLimit(10);
    final trial = app.measureDevice();
    app.setFocusLimit(100);
    result.complete(SearchResponse(mode: 'device_trial', raw: {'cpu_ms': 100, 'gpu': false}));
    await trial;
    expect(app.focusChoice!.k, 100);
    expect(app.focusLimit, 100);
  });

  test('old search timings cannot disable a newly selected limit', () {
    final app = AppController.fixed();
    addTearDown(app.dispose);
    app.user.setPref('answer_focus_choice', const FocusChoice(FocusModel.ezra, FocusVariant.int8, 10, 100).toJson());
    final previous = app.focusChoice!;
    app.recordFocusTime(50000);
    app.recordFocusTime(50000);
    app.setFocusLimit(100);
    for (var i = 0; i < 3; i++) {
      app.recordFocusTime(50000, choice: previous);
    }
    app.recordFocusTime(50000, choice: app.focusChoice);
    expect(app.focusChoice!.k, 100, reason: 'new settings start with fresh timing samples');
    app.recordFocusTime(50000);
    app.recordFocusTime(50000);
    expect(app.focusChoice, FocusChoice.none);
    expect(app.focusLimit, 100, reason: 'Automatic may disable scoring, but retains the selected count');
  });
}
