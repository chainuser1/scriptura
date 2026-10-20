// Settings' Ezra/Apollos model picker: both choices always visible and enabled, selecting Apollos re-measures and
// warns (with an explicit choice to proceed or fall back) when the device does not fit it.
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

  testWidgets('both Ezra and Apollos are always visible and enabled', (tester) async {
    await settings(tester);
    expect(find.text('Ezra'), findsOneWidget);
    expect(find.text('Apollos'), findsOneWidget);
    final picker = tester.widget<SegmentedButton<FocusModel>>(find.byType(SegmentedButton<FocusModel>).last);
    expect(picker.segments.firstWhere((s) => s.value == FocusModel.apollos).enabled, isTrue);
  });

  testWidgets('Ezra is the default preference', (tester) async {
    final (app, _) = await settings(tester);
    expect(app.focusModelPreference, FocusModel.ezra);
  });

  testWidgets('choosing Ezra sets the preference and remeasures', (tester) async {
    final (app, svc) = await settings(tester);
    svc.requests.clear();
    await tester.ensureVisible(find.text('Apollos'));
    await tester.tap(find.text('Apollos'));
    await tester.pumpAndSettle();
    svc.requests.clear();
    await tester.ensureVisible(find.text('Ezra'));
    await tester.tap(find.text('Ezra'));
    await tester.pumpAndSettle();
    expect(app.focusModelPreference, FocusModel.ezra);
    expect(svc.requests.map((r) => r.op), contains('device_trial')); // remeasure() ran a fresh trial
  });

  testWidgets('choosing Apollos on a device it fits just switches, no dialog', (tester) async {
    // cpuMs chosen so Apollos's own ladder fits comfortably (far under its 15000ms budget at k=10).
    final (app, _) = await settings(tester, cpuMs: 200.0);
    await tester.ensureVisible(find.text('Apollos'));
    await tester.tap(find.text('Apollos'));
    await tester.pumpAndSettle();
    expect(app.focusModelPreference, FocusModel.apollos);
    expect(app.focusChoice!.model, FocusModel.apollos);
    expect(find.byType(AlertDialog), findsNothing);
  });

  testWidgets('choosing Apollos on a device it does not fit warns, and "Use Ezra instead" falls back', (tester) async {
    // cpuMs chosen so Ezra's ladder fits (k=10) but Apollos's own (much heavier, much longer budget) ladder does not.
    final (app, _) = await settings(tester, cpuMs: 1800.0);
    await tester.ensureVisible(find.text('Apollos'));
    await tester.tap(find.text('Apollos'));
    await tester.pumpAndSettle();
    expect(find.textContaining('may not be fast enough'), findsOneWidget);
    await tester.tap(find.text('Use Ezra instead'));
    await tester.pumpAndSettle();
    expect(app.focusModelPreference, FocusModel.ezra);
    expect(app.apollosOverrideAccepted, isFalse);
  });

  testWidgets('choosing Apollos on a device it does not fit, then "Try Apollos anyway" keeps Apollos', (tester) async {
    final (app, _) = await settings(tester, cpuMs: 1800.0);
    await tester.ensureVisible(find.text('Apollos'));
    await tester.tap(find.text('Apollos'));
    await tester.pumpAndSettle();
    expect(find.textContaining('may not be fast enough'), findsOneWidget);
    await tester.tap(find.text('Try Apollos anyway'));
    await tester.pumpAndSettle();
    expect(app.focusModelPreference, FocusModel.apollos);
    expect(app.apollosOverrideAccepted, isTrue);
    expect(app.focusChoice!.model, FocusModel.apollos); // the override made it stick despite not fitting
  });

  testWidgets('once the override is accepted, re-measuring does not warn again', (tester) async {
    final (app, _) = await settings(tester, cpuMs: 1800.0);
    await tester.ensureVisible(find.text('Apollos'));
    await tester.tap(find.text('Apollos'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Try Apollos anyway'));
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.text('Measure again'));
    await tester.tap(find.text('Measure again'));
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsNothing);
    expect(app.focusChoice!.model, FocusModel.apollos);
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
    await tester.tap(find.text('Apollos'));
    await tester.pumpAndSettle();
    expect(app.focusModelPreference, FocusModel.ezra, reason: 'a disabled picker does not change the preference');
  });
}
