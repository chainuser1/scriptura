import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app/nav_state.dart';
import 'package:scriptures_reader_mobile/app_controller.dart';
import 'package:scriptures_reader_mobile/data/content/catalog.dart';
import 'package:scriptures_reader_mobile/data/content/content_database.dart';
import 'package:scriptures_reader_mobile/data/content/content_repository.dart';
import 'package:scriptures_reader_mobile/data/user/user_store.dart';
import 'package:scriptures_reader_mobile/main.dart';

import 'fakes/fake_search_service.dart';

ContentRepository fixtureRepository() {
  final db = ContentDatabase.open('test/fixtures/content_v2_mini.db');
  return ContentRepository(db, Catalog.load('test/fixtures/catalog_mini.db', contract: db.contract));
}

Future<AppController> bootPhone(WidgetTester tester, {double statusBar = 0, double height = 780}) async {
  tester.view.physicalSize = Size(390, height);
  tester.view.devicePixelRatio = 1;
  tester.view.padding = FakeViewPadding(top: statusBar);
  tester.view.viewPadding = FakeViewPadding(top: statusBar);
  addTearDown(tester.view.reset);
  final app = AppController.fixed(repository: fixtureRepository(), search: FakeSearchService((r, i) async => semantic([2])), user: UserStore.memory());
  await tester.pumpWidget(ScripturesReaderApp(app: app));
  await tester.pumpAndSettle();
  return app;
}

void main() {
  testWidgets('the reader has floating previous and next chapter buttons that work from anywhere in the chapter', (tester) async {
    final app = await bootPhone(tester);
    app.nav.openChapter(1, 1);
    await tester.pumpAndSettle();
    expect(find.byTooltip('Previous chapter'), findsNothing); // first chapter of the first book
    expect(find.byTooltip('Next chapter'), findsOneWidget);
    await tester.tap(find.byTooltip('Next chapter'));
    await tester.pumpAndSettle();
    expect(app.nav.chapter, 2);
    expect(find.byTooltip('Previous chapter'), findsOneWidget);
    await tester.tap(find.byTooltip('Previous chapter'));
    await tester.pumpAndSettle();
    expect(app.nav.chapter, 1);
  });

  testWidgets('the floating buttons step aside while the page is being scrolled and come back', (tester) async {
    final app = await bootPhone(tester, height: 330);
    app.nav.openChapter(1, 1);
    await tester.pumpAndSettle();
    final fade = find.ancestor(of: find.byTooltip('Next chapter'), matching: find.byType(AnimatedOpacity));
    expect(tester.widget<AnimatedOpacity>(fade.first).opacity, greaterThan(0));
    await tester.drag(find.byType(Scrollable).first, const Offset(0, -40));
    await tester.pump(const Duration(milliseconds: 50));
    expect(tester.widget<AnimatedOpacity>(fade.first).opacity, 0);
    await tester.pumpAndSettle(const Duration(seconds: 2));
    expect(tester.widget<AnimatedOpacity>(fade.first).opacity, greaterThan(0));
  });

  testWidgets('content stays clear of the phone status bar on every screen', (tester) async {
    const bar = 48.0;
    final app = await bootPhone(tester, statusBar: bar);
    for (final d in [Dest.home, Dest.search, Dest.study, Dest.settings]) {
      app.nav.go(d);
      await tester.pumpAndSettle();
      final top = tester.getTopLeft(find.descendant(of: find.byType(Scaffold), matching: find.byType(IndexedStack)).first).dy;
      // find the highest piece of visible text or field on the page
      double highest = double.infinity;
      for (final f in [find.byType(TextField), find.byType(TabBar), find.byType(Text)]) {
        for (final e in f.evaluate()) {
          final box = e.renderObject as RenderBox?;
          if (box == null || !box.attached || !box.hasSize) continue;
          final y = box.localToGlobal(Offset.zero).dy;
          if (y >= 0 && y < highest) {
            highest = y;
          }
        }
      }
      expect(highest, greaterThanOrEqualTo(bar), reason: '$d draws into the status bar (top=$top)');
    }
  });
}
