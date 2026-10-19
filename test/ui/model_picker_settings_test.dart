// Settings' Ezra/Apollos model picker: both choices always visible, selecting changes the preference and triggers a
// remeasure, and the one-time "working on a solution" notice gives way to a quiet greyed state.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app/nav_state.dart';
import 'package:scriptures_reader_mobile/app_controller.dart';
import 'package:scriptures_reader_mobile/services/engine/answer_focus.dart';
import 'package:scriptures_reader_mobile/services/engine/search_models.dart';

import '../fakes/fake_search_service.dart';
import '../widget_test.dart' show boot;

void main() {
  Future<(AppController, FakeSearchService)> settings(
    WidgetTester tester, {
    bool gpu = false,
    double cpuMs = 1839.0,
  }) async {
    final svc = FakeSearchService(
      (r, id) async => r.op == 'device_trial' ? SearchResponse(mode: 'device_trial', raw: {'cpu_ms': cpuMs, 'gpu': gpu}) : semantic([1]),
    );
    final app = await boot(tester, search: svc);
    app.nav.go(Dest.settings);
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Answer focus'), 300, scrollable: find.byType(Scrollable).last);
    await tester.pumpAndSettle();
    return (app, svc);
  }

  testWidgets('both Ezra and Apollos are always visible as choices', (tester) async {
    await settings(tester);
    expect(find.text('Ezra'), findsOneWidget);
    expect(find.text('Apollos'), findsOneWidget);
  });

  testWidgets('choosing Ezra sets the preference and remeasures', (tester) async {
    final (app, svc) = await settings(tester);
    svc.requests.clear();
    await tester.ensureVisible(find.text('Ezra'));
    await tester.tap(find.text('Ezra'));
    await tester.pumpAndSettle();
    expect(app.focusModelPreference, FocusModel.ezra);
    expect(svc.requests.map((r) => r.op), contains('device_trial')); // remeasure() ran a fresh trial
  });

  testWidgets('a device where Apollos never resolves shows the notice once, then a quiet greyed state', (tester) async {
    // cpuMs chosen so Ezra's int8 ladder still fits at k=10 (1500 * 0.069 * 10 = 1035ms, under the 1500ms budget) but
    // Apollos's (double the per-candidate cost) does not even at k=10 (1500 * 0.138 * 10 = 2070ms, over budget), and
    // no gpu, so with Apollos preferred the trial falls back to Ezra -- Apollos "didn't resolve here".
    final (app, _) = await settings(tester, gpu: false, cpuMs: 1500.0);
    expect(app.focusModelPreference, FocusModel.apollos);
    await tester.ensureVisible(find.text('Measure again'));
    await tester.tap(find.text('Measure again'));
    await tester.pumpAndSettle();
    expect(app.focusChoice!.model, FocusModel.ezra); // fell back
    // The prominent notice stays (across frames) until the reader acknowledges it.
    expect(find.textContaining('Scriptura Labs is working on a solution'), findsOneWidget);
    expect(app.apollosUnavailableNoticeShown, isFalse);
    await tester.tap(find.text('Got it'));
    await tester.pumpAndSettle();
    expect(app.apollosUnavailableNoticeShown, isTrue);
    expect(find.text('Got it'), findsNothing);

    // Leave and come back: the prominent notice is gone, replaced by the quiet greyed state.
    app.nav.go(Dest.home);
    await tester.pumpAndSettle();
    app.nav.go(Dest.settings);
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Answer focus'), 300, scrollable: find.byType(Scrollable).last);
    await tester.pumpAndSettle();
    expect(find.textContaining('Scriptura Labs is working on a solution'), findsNothing);
    expect(find.textContaining('isn\'t available on this device yet'), findsOneWidget);

    final apollosSegment = tester.widget<SegmentedButton<FocusModel>>(find.byType(SegmentedButton<FocusModel>).last);
    expect(apollosSegment.segments.firstWhere((s) => s.value == FocusModel.apollos).enabled, isFalse);
  });

  testWidgets('an old Ezra choice never trialled under Apollos is not reported as Apollos being unavailable', (tester) async {
    final (app, _) = await settings(tester);
    // An upgrade: a persisted Ezra choice from before Apollos, with no recorded trial preference.
    app.user.setPref('answer_focus_choice', const FocusChoice(FocusModel.ezra, FocusVariant.int8, 10, 1200).toJson());
    await tester.pumpAndSettle();
    expect(app.focusTrialPreference, isNull);
    expect(app.focusModelPreference, FocusModel.apollos);
    expect(find.textContaining('Scriptura Labs is working on a solution'), findsNothing);
    expect(find.textContaining('isn\'t available on this device yet'), findsNothing);
    final picker = tester.widget<SegmentedButton<FocusModel>>(find.byType(SegmentedButton<FocusModel>));
    expect(picker.segments.firstWhere((s) => s.value == FocusModel.apollos).enabled, isTrue);
  });

  testWidgets('the whole model picker is disabled while the engine is not ready', (tester) async {
    final app = await boot(tester); // no search service: the engine is unavailable
    expect(app.engineState, isNot(EngineState.ready));
    app.nav.go(Dest.settings);
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Answer focus'), 300, scrollable: find.byType(Scrollable).last);
    await tester.pumpAndSettle();
    final picker = tester.widget<SegmentedButton<FocusModel>>(find.byType(SegmentedButton<FocusModel>));
    expect(picker.onSelectionChanged, isNull);
    await tester.tap(find.text('Ezra'));
    await tester.pumpAndSettle();
    expect(app.focusModelPreference, FocusModel.apollos, reason: 'a disabled picker does not change the preference');
  });
}
