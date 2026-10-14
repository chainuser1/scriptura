// Accessibility checks on the main screens: every tappable control is labelled, text contrast is sufficient, verses are
// reachable and operable from the keyboard, and the semantics tree describes verses sensibly.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app/nav_state.dart';
import 'package:scriptures_reader_mobile/app_controller.dart';
import 'package:scriptures_reader_mobile/data/content/catalog.dart';
import 'package:scriptures_reader_mobile/data/content/content_database.dart';
import 'package:scriptures_reader_mobile/data/content/content_repository.dart';
import 'package:scriptures_reader_mobile/data/user/user_store.dart';
import 'package:scriptures_reader_mobile/main.dart';

import '../fakes/fake_search_service.dart';

ContentRepository fixtureRepository() {
  final db = ContentDatabase.open('test/fixtures/content_v2_mini.db');
  return ContentRepository(db, Catalog.load('test/fixtures/catalog_mini.db', contract: db.contract));
}

Future<AppController> boot(WidgetTester tester, {String theme = 'paper'}) async {
  tester.view.physicalSize = const Size(1280, 800);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final user = UserStore.memory()..setPref('reading_theme', theme);
  user.toggleBookmark(2);
  user.toggleHighlight(3, 1);
  final app = AppController.fixed(repository: fixtureRepository(), search: FakeSearchService((r, i) async => semantic([2, 5])), user: user);
  await tester.pumpWidget(ScripturesReaderApp(app: app));
  await tester.pumpAndSettle();
  return app;
}

void main() {
  for (final entry in {
    'home': Dest.home,
    'read': Dest.read,
    'search': Dest.search,
    'study': Dest.study,
    'settings': Dest.settings,
  }.entries) {
    testWidgets('${entry.key}: controls are labelled and text has enough contrast', (tester) async {
      final handle = tester.ensureSemantics();
      final app = await boot(tester);
      if (entry.value == Dest.read) app.nav.openChapter(1, 1);
      app.nav.go(entry.value);
      await tester.pumpAndSettle();
      await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
      await expectLater(tester, meetsGuideline(textContrastGuideline));
      handle.dispose();
    });
  }

  for (final theme in ['sepia', 'night']) {
    testWidgets('reading in the $theme theme keeps text contrast', (tester) async {
      final handle = tester.ensureSemantics();
      final app = await boot(tester, theme: theme);
      app.nav.openChapter(1, 1);
      await tester.pumpAndSettle();
      await expectLater(tester, meetsGuideline(textContrastGuideline));
      handle.dispose();
    });
  }

  testWidgets('a verse is announced with its number and state, and opens from the keyboard', (tester) async {
    final handle = tester.ensureSemantics();
    final app = await boot(tester);
    app.nav.openChapter(1, 1);
    await tester.pumpAndSettle();
    expect(find.bySemanticsLabel(RegExp(r'^Verse 2, bookmarked')), findsOneWidget);
    expect(find.bySemanticsLabel(RegExp(r'^Verse 3, highlighted')), findsOneWidget);

    // focus a verse (as Tab would) and activate it with Enter
    final inside = tester.element(find.descendant(of: find.byKey(const ValueKey('verse-1-true')), matching: find.byType(Container)).first);
    Focus.of(inside).requestFocus();
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(find.text('Copy with reference'), findsOneWidget, reason: 'a focused verse must open its menu with Enter');
    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pumpAndSettle();
    expect(find.text('Copy with reference'), findsNothing);
    handle.dispose();
  });
}
