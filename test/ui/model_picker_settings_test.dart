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
    // Apollos's 40s budget is generous, so this only happens on a genuinely very slow device: at this speed
    // Apollos's own ladder exceeds 40s even at k=10, and under Automatic mode (the default here) Ezra's own
    // 1500ms budget fails too at every k, landing on FocusVariant.none -- still "Apollos did not fit".
    final (app, _) = await settings(tester, cpuMs: 4200.0);
    await tester.ensureVisible(find.text('Apollos'));
    await tester.tap(find.text('Apollos'));
    await tester.pumpAndSettle();
    expect(find.textContaining('may not be fast enough'), findsOneWidget);
    await tester.tap(find.text('Use Ezra instead'));
    await tester.pumpAndSettle();
    expect(app.focusModelPreference, FocusModel.ezra);
    expect(app.overrideAccepted(FocusModel.apollos), isFalse);
  });

  testWidgets('choosing Apollos on a device it does not fit, then "Try Apollos anyway" keeps Apollos', (tester) async {
    final (app, _) = await settings(tester, cpuMs: 4200.0);
    await tester.ensureVisible(find.text('Apollos'));
    await tester.tap(find.text('Apollos'));
    await tester.pumpAndSettle();
    expect(find.textContaining('may not be fast enough'), findsOneWidget);
    await tester.tap(find.text('Try Apollos anyway'));
    await tester.pumpAndSettle();
    expect(app.focusModelPreference, FocusModel.apollos);
    expect(app.overrideAccepted(FocusModel.apollos), isTrue);
    expect(app.focusChoice!.model, FocusModel.apollos); // the override made it stick despite not fitting
  });

  testWidgets('once the override is accepted, re-measuring does not warn again', (tester) async {
    final (app, _) = await settings(tester, cpuMs: 4200.0);
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

  testWidgets('Ezra, Apollos, and Priscilla are all visible and enabled', (tester) async {
    await settings(tester);
    expect(find.text('Ezra'), findsOneWidget);
    expect(find.text('Apollos'), findsOneWidget);
    expect(find.text('Priscilla'), findsOneWidget);
    final picker = tester.widget<SegmentedButton<FocusModel>>(find.byType(SegmentedButton<FocusModel>).last);
    expect(picker.segments.firstWhere((s) => s.value == FocusModel.priscilla).enabled, isTrue);
  });

  testWidgets('choosing Priscilla on a device it fits just switches, no dialog', (tester) async {
    // cpuMs chosen so Priscilla's own (now Apollos-sized) ladder fits comfortably.
    final (app, _) = await settings(tester, cpuMs: 200.0);
    await tester.ensureVisible(find.text('Priscilla'));
    await tester.tap(find.text('Priscilla'));
    await tester.pumpAndSettle();
    expect(app.focusModelPreference, FocusModel.priscilla);
    expect(app.focusChoice!.model, FocusModel.priscilla);
    expect(find.byType(AlertDialog), findsNothing);
  });

  testWidgets('choosing Priscilla on a device it does not fit warns, and "Use Ezra instead" falls back', (tester) async {
    final (app, _) = await settings(tester, cpuMs: 100000.0);
    await tester.ensureVisible(find.text('Priscilla'));
    await tester.tap(find.text('Priscilla'));
    await tester.pumpAndSettle();
    expect(find.textContaining('may not be fast enough'), findsOneWidget);
    await tester.tap(find.text('Use Ezra instead'));
    await tester.pumpAndSettle();
    expect(app.focusModelPreference, FocusModel.ezra);
    expect(app.overrideAccepted(FocusModel.priscilla), isFalse);
  });

  testWidgets('choosing Priscilla on a device it does not fit, then "Try Priscilla anyway" keeps Priscilla', (tester) async {
    final (app, _) = await settings(tester, cpuMs: 100000.0);
    await tester.ensureVisible(find.text('Priscilla'));
    await tester.tap(find.text('Priscilla'));
    await tester.pumpAndSettle();
    expect(find.textContaining('may not be fast enough'), findsOneWidget);
    await tester.tap(find.text('Try Priscilla anyway'));
    await tester.pumpAndSettle();
    expect(app.focusModelPreference, FocusModel.priscilla);
    expect(app.overrideAccepted(FocusModel.priscilla), isTrue);
    expect(app.focusChoice!.model, FocusModel.priscilla);
  });

  testWidgets('switching from an overridden Apollos to Priscilla on a slow device still shows Priscilla\'s own '
      'warning (end-to-end flow; the override store\'s actual per-model isolation is unit-tested directly in '
      'app_controller_focus_notice_test.dart, since switching models here always resets the other model\'s flag '
      'by design -- this widget test cannot isolate that on its own, only prove the whole flow still works)', (tester) async {
    final (app, _) = await settings(tester, cpuMs: 100000.0);
    await tester.ensureVisible(find.text('Apollos'));
    await tester.tap(find.text('Apollos'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Try Apollos anyway'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Priscilla'));
    await tester.tap(find.text('Priscilla'));
    await tester.pumpAndSettle();
    expect(find.textContaining('may not be fast enough'), findsOneWidget,
        reason: 'Priscilla must still warn even though Apollos was already overridden');
  });

  testWidgets('switching directly from Priscilla to Apollos works without going through Ezra first', (tester) async {
    final (app, _) = await settings(tester, cpuMs: 200.0);
    await tester.ensureVisible(find.text('Priscilla'));
    await tester.tap(find.text('Priscilla'));
    await tester.pumpAndSettle();
    expect(app.focusModelPreference, FocusModel.priscilla);
    await tester.ensureVisible(find.text('Apollos'));
    await tester.tap(find.text('Apollos'));
    await tester.pumpAndSettle();
    expect(app.focusModelPreference, FocusModel.apollos);
  });

  testWidgets('switching directly from Apollos to Priscilla works without going through Ezra first', (tester) async {
    final (app, _) = await settings(tester, cpuMs: 200.0);
    await tester.ensureVisible(find.text('Apollos'));
    await tester.tap(find.text('Apollos'));
    await tester.pumpAndSettle();
    expect(app.focusModelPreference, FocusModel.apollos);
    await tester.ensureVisible(find.text('Priscilla'));
    await tester.tap(find.text('Priscilla'));
    await tester.pumpAndSettle();
    expect(app.focusModelPreference, FocusModel.priscilla);
    expect(find.byType(AlertDialog), findsNothing);
  });

  testWidgets('Priscilla has its own description text reflecting its slower, experimental tradeoff', (tester) async {
    final (app, _) = await settings(tester, cpuMs: 200.0);
    await tester.ensureVisible(find.text('Priscilla'));
    await tester.tap(find.text('Priscilla'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Priscilla'), findsWidgets);
    expect(find.textContaining('than Ezra'), findsOneWidget, reason: 'a phrase only in Priscilla\'s own copy, not Apollos\'s near-identical text');
  });

  testWidgets('Ezra, Apollos, Priscilla, and Aquila are all visible and enabled', (tester) async {
    await settings(tester);
    expect(find.text('Ezra'), findsOneWidget);
    expect(find.text('Apollos'), findsOneWidget);
    expect(find.text('Priscilla'), findsOneWidget);
    expect(find.text('Aquila'), findsOneWidget);
    final picker = tester.widget<SegmentedButton<FocusModel>>(find.byType(SegmentedButton<FocusModel>).last);
    expect(picker.segments.firstWhere((s) => s.value == FocusModel.aquila).enabled, isTrue);
  });

  testWidgets('choosing Aquila on a device it fits just switches, no dialog', (tester) async {
    final (app, _) = await settings(tester, cpuMs: 200.0);
    await tester.ensureVisible(find.text('Aquila'));
    await tester.tap(find.text('Aquila'));
    await tester.pumpAndSettle();
    expect(app.focusModelPreference, FocusModel.aquila);
    expect(app.focusChoice!.model, FocusModel.aquila);
    expect(find.byType(AlertDialog), findsNothing);
  });

  testWidgets('choosing Aquila on a device it does not fit warns, and "Use Ezra instead" falls back', (tester) async {
    final (app, _) = await settings(tester, cpuMs: 4200.0);
    await tester.ensureVisible(find.text('Aquila'));
    await tester.tap(find.text('Aquila'));
    await tester.pumpAndSettle();
    expect(find.textContaining('may not be fast enough'), findsOneWidget);
    await tester.tap(find.text('Use Ezra instead'));
    await tester.pumpAndSettle();
    expect(app.focusModelPreference, FocusModel.ezra);
    expect(app.overrideAccepted(FocusModel.aquila), isFalse);
  });

  testWidgets('choosing Aquila on a device it does not fit, then "Try Aquila anyway" keeps Aquila', (tester) async {
    final (app, _) = await settings(tester, cpuMs: 4200.0);
    await tester.ensureVisible(find.text('Aquila'));
    await tester.tap(find.text('Aquila'));
    await tester.pumpAndSettle();
    expect(find.textContaining('may not be fast enough'), findsOneWidget);
    await tester.tap(find.text('Try Aquila anyway'));
    await tester.pumpAndSettle();
    expect(app.focusModelPreference, FocusModel.aquila);
    expect(app.overrideAccepted(FocusModel.aquila), isTrue);
    expect(app.focusChoice!.model, FocusModel.aquila);
  });

  testWidgets('switching directly from Aquila to Apollos works without going through Ezra first', (tester) async {
    final (app, _) = await settings(tester, cpuMs: 200.0);
    await tester.ensureVisible(find.text('Aquila'));
    await tester.tap(find.text('Aquila'));
    await tester.pumpAndSettle();
    expect(app.focusModelPreference, FocusModel.aquila);
    await tester.ensureVisible(find.text('Apollos'));
    await tester.tap(find.text('Apollos'));
    await tester.pumpAndSettle();
    expect(app.focusModelPreference, FocusModel.apollos);
  });

  testWidgets('switching directly from Priscilla to Aquila works without going through Ezra first', (tester) async {
    final (app, _) = await settings(tester, cpuMs: 200.0);
    await tester.ensureVisible(find.text('Priscilla'));
    await tester.tap(find.text('Priscilla'));
    await tester.pumpAndSettle();
    expect(app.focusModelPreference, FocusModel.priscilla);
    await tester.ensureVisible(find.text('Aquila'));
    await tester.tap(find.text('Aquila'));
    await tester.pumpAndSettle();
    expect(app.focusModelPreference, FocusModel.aquila);
    expect(find.byType(AlertDialog), findsNothing);
  });

  testWidgets('Aquila has its own description text', (tester) async {
    final (app, _) = await settings(tester, cpuMs: 200.0);
    await tester.ensureVisible(find.text('Aquila'));
    await tester.tap(find.text('Aquila'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Aquila'), findsWidgets);
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
