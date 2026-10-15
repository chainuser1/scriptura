import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app_controller.dart';
import 'package:scriptures_reader_mobile/data/trails/trail_models.dart';
import 'package:scriptures_reader_mobile/data/user/user_store.dart';
import 'package:scriptures_reader_mobile/main.dart';

import '../fakes/fake_search_service.dart';
import 'trail_harness.dart';

Future<AppController> boot(WidgetTester tester, {Size size = const Size(1280, 800)}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final svc = FakeSearchService((r, id) async => batchOf([2, 3, 4]));
  final app = AppController.fixed(repository: fixtureRepository(), search: svc, user: UserStore.memory());
  await tester.pumpWidget(ScripturesReaderApp(app: app));
  await tester.pumpAndSettle();
  return app;
}

void main() {
  testWidgets('Home offers the eight starter trails and one tap opens a trail', (tester) async {
    final app = await boot(tester);
    expect(find.text('Start a trail'), findsOneWidget);
    for (final title in ['Finding comfort', 'Hope when it is dark', 'Serving others']) {
      expect(find.text(title), findsOneWidget, reason: title);
    }
    await tester.tap(find.text('Finding comfort'));
    await tester.pumpAndSettle();
    expect(find.text('Like'), findsOneWidget);
    final t = app.user.trails().single;
    expect(t.seed.kind, TrailSeedKind.question);
    expect(t.moods, ['comfort']);
  });

  testWidgets('leaving a trail shows the return bar on every screen and Resume reopens it', (tester) async {
    await boot(tester);
    await tester.tap(find.text('Finding comfort'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Back'));
    await tester.pumpAndSettle();
    expect(find.text('Resume'), findsOneWidget);
    await tester.tap(find.descendant(of: find.byType(NavigationRail), matching: find.text('Settings')));
    await tester.pumpAndSettle();
    expect(find.text('Resume'), findsOneWidget);
    await tester.tap(find.text('Resume'));
    await tester.pumpAndSettle();
    expect(find.text('Like'), findsOneWidget);
    expect(find.text('Resume'), findsNothing); // hidden on the Trail page
  });

  testWidgets('the return bar can be dismissed and a trail with no activity never shows it', (tester) async {
    final app = await boot(tester);
    app.user.createTrail(name: 'Never opened', seed: const TrailSeed.verse(1));
    app.user.setPref('active_trail', app.user.trails().single.id);
    await tester.pumpAndSettle();
    expect(find.text('Resume'), findsNothing);
    final id = app.user.trails().single.id;
    app.user.addTrailEvent(id, 2, TrailAction.shown);
    await tester.pumpAndSettle();
    expect(find.text('Resume'), findsOneWidget);
    await tester.tap(find.byTooltip('Dismiss'));
    await tester.pumpAndSettle();
    expect(find.text('Resume'), findsNothing);
  });

  testWidgets('Study has a Trails tab listing trails with Undo on delete', (tester) async {
    final app = await boot(tester);
    final t = app.user.createTrail(name: 'Mercy trail', seed: const TrailSeed.verse(1));
    app.user.addTrailEvent(t.id, 2, TrailAction.shown);
    await tester.tap(find.descendant(of: find.byType(NavigationRail), matching: find.text('Study')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Trails'));
    await tester.pumpAndSettle();
    expect(find.text('Mercy trail'), findsOneWidget);
    await tester.tap(find.byTooltip('More'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete'));
    await tester.pumpAndSettle();
    expect(app.user.trail(t.id), isNull);
    expect(find.byType(AlertDialog), findsNothing);
    await tester.tap(find.text('Undo'));
    await tester.pumpAndSettle();
    expect(app.user.trail(t.id)!.name, 'Mercy trail');
  });

  testWidgets('narrow phone width: starters wrap with no overflow and the return bar sits above the navigation bar', (tester) async {
    await boot(tester, size: const Size(360, 640));
    expect(tester.takeException(), isNull);
    await tester.ensureVisible(find.text('Finding comfort')); // below the fold on a phone: reached by scrolling
    await tester.pumpAndSettle();
    await tester.tap(find.text('Finding comfort'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Back'));
    await tester.pumpAndSettle();
    expect(find.text('Resume'), findsOneWidget);
    expect(tester.getBottomLeft(find.text('Resume')).dy, lessThan(tester.getTopLeft(find.byType(NavigationBar)).dy));
    expect(tester.takeException(), isNull);
  });
}
