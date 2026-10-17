import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app/nav_state.dart';
import 'package:scriptures_reader_mobile/app_controller.dart';
import 'package:scriptures_reader_mobile/features/about/about_screen.dart';
import 'package:scriptures_reader_mobile/services/engine/answer_focus.dart';
import 'package:scriptures_reader_mobile/services/engine/search_models.dart';

import '../fakes/fake_search_service.dart';
import '../widget_test.dart' show boot;

void main() {
  Future<(AppController, FakeSearchService)> settings(WidgetTester tester, {bool hasFocus = false, FocusChoice? choice}) async {
    final svc = FakeSearchService(
      (r, id) async => r.op == 'device_trial' ? SearchResponse(mode: 'device_trial', raw: {'cpu_ms': 1839.0, 'gpu': false}) : semantic([1]),
      hasFocus: hasFocus,
    );
    final app = await boot(tester, search: svc);
    if (choice != null) app.user.setPref('answer_focus_choice', choice.toJson());
    app.nav.go(Dest.settings);
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Answer focus'), 300, scrollable: find.byType(Scrollable).last);
    await tester.pumpAndSettle();
    return (app, svc);
  }

  testWidgets('Advanced offers Automatic, On and Off', (tester) async {
    final (app, _) = await settings(tester);
    expect(find.text('Automatic'), findsOneWidget);
    expect(find.text('On'), findsOneWidget);
    await tester.ensureVisible(find.text('Off'));
    await tester.tap(find.text('Off'));
    await tester.pumpAndSettle();
    expect(app.focusMode, FocusMode.off);
    expect(find.textContaining('Off: search works as usual'), findsOneWidget);
  });

  testWidgets('Measure again runs the device trial and says what it chose', (tester) async {
    final (app, svc) = await settings(tester);
    expect(find.textContaining('Not measured yet'), findsOneWidget);
    await tester.ensureVisible(find.text('Measure again'));
    await tester.tap(find.text('Measure again'));
    await tester.pumpAndSettle();
    expect(svc.requests.map((r) => r.op), contains('device_trial'));
    expect(app.focusChoice!.variant, FocusVariant.int8);
    expect(find.textContaining('the processor'), findsOneWidget);
  });

  testWidgets('says what it is using once installed', (tester) async {
    await settings(tester, hasFocus: true, choice: const FocusChoice(FocusVariant.fp16, 10, 1200));
    expect(find.textContaining('Using the graphics chip'), findsOneWidget);
  });

  testWidgets('a device too slow for it is told plainly', (tester) async {
    await settings(tester, choice: FocusChoice.none);
    expect(find.textContaining('too slow'), findsOneWidget);
  });

  testWidgets('credits name the model and its licence', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: AboutScreen()));
    await tester.scrollUntilVisible(find.textContaining('bge-reranker-v2-m3'), 300, scrollable: find.byType(Scrollable).first);
    expect(find.textContaining('Apache'), findsOneWidget);
  });

  test('the app never calls it a reranker (only the model\'s own name)', () {
    for (final f in Directory('lib').listSync(recursive: true).whereType<File>().where((f) => f.path.endsWith('.dart'))) {
      final text = f.readAsStringSync().toLowerCase().replaceAll('bge-reranker-v2-m3', '');
      expect(text.contains('reranker'), isFalse, reason: f.path);
    }
  });
}
