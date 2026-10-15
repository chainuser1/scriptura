import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app/looks.dart';
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

Future<AppController> boot(WidgetTester tester, {Size size = const Size(390, 800)}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final app = AppController.fixed(repository: fixtureRepository(), search: FakeSearchService((r, i) async => semantic([2])), user: UserStore.memory());
  await tester.pumpWidget(ScripturesReaderApp(app: app));
  await tester.pumpAndSettle();
  return app;
}

void main() {
  testWidgets('Settings shows the looks first; one tap applies a look and the controls say Custom once changed', (tester) async {
    final app = await boot(tester);
    app.nav.go(Dest.settings);
    await tester.pumpAndSettle();
    expect(find.text('LOOK AND FEEL'), findsOneWidget);
    expect(find.text('Book'), findsOneWidget);
    await tester.tap(find.text('E-reader'));
    await tester.pumpAndSettle();
    expect(app.user.pref('reading_theme'), 'sepia');
    expect(app.user.pref('reading_font'), 'literata');
    expect(lookOf(app.user)?.id, 'ereader');

    await tester.tap(find.text('Fine-tune the look'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byTooltip('Forest'));
    await tester.tap(find.byTooltip('Forest'));
    await tester.pumpAndSettle();
    expect(app.user.pref('reading_theme'), 'forest');
    expect(lookOf(app.user), isNull);
    await tester.drag(find.byType(ListView).first, const Offset(0, 2000)); // back to the top, where the gallery says so
    await tester.pumpAndSettle();
    expect(find.textContaining('Custom'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the reader has an Aa menu with the looks and the quick controls', (tester) async {
    final app = await boot(tester);
    app.nav.openChapter(1, 1);
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Reading look, text size and colour'));
    await tester.pumpAndSettle();
    expect(find.text('Reading look'), findsOneWidget);
    // the looks are a swipeable row; the last one is reached by swiping
    await tester.dragUntilVisible(find.text('Large print'), find.descendant(of: find.byType(BottomSheet), matching: find.byType(ListView)), const Offset(-150, 0));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Large print'));
    await tester.pumpAndSettle();
    expect(app.user.pref('text_scale'), '1.50');
    expect(app.user.pref('reading_theme'), 'contrast');
    expect(find.text('All reading settings'), findsOneWidget);
    await tester.ensureVisible(find.text('All reading settings'));
    await tester.tap(find.text('All reading settings'));
    await tester.pumpAndSettle();
    expect(app.nav.dest, Dest.settings);
    expect(tester.takeException(), isNull);
  });

  testWidgets('verse numbers can sit inline, in the margin, or be hidden', (tester) async {
    final app = await boot(tester);
    app.nav.openChapter(1, 1);
    await tester.pumpAndSettle();
    expect(find.textContaining('1  '), findsWidgets, reason: 'inline by default');
    app.user.setPref('verse_numbers', 'margin');
    await tester.pumpAndSettle();
    expect(find.textContaining('1  '), findsNothing);
    expect(find.text('1'), findsOneWidget);
    app.user.setPref('verse_numbers', 'hidden');
    await tester.pumpAndSettle();
    expect(find.text('1'), findsNothing);
    expect(find.textContaining('1  '), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the cards layout puts each verse on a card with its menu button in reach', (tester) async {
    final app = await boot(tester);
    app.nav.openChapter(1, 1);
    await tester.pumpAndSettle();
    expect(find.byTooltip('Verse menu'), findsNothing);
    app.user.setPref('verse_layout', 'cards');
    await tester.pumpAndSettle();
    expect(find.byTooltip('Verse menu'), findsNWidgets(3));
    await tester.tap(find.byTooltip('Verse menu').first);
    await tester.pumpAndSettle();
    expect(find.text('Copy with reference'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('every look reads without layout errors on a phone and a desktop window', (tester) async {
    for (final size in const [Size(360, 640), Size(1280, 800)]) {
      final app = await boot(tester, size: size);
      app.nav.openChapter(1, 1);
      for (final look in looks) {
        applyLook(app.user, look);
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull, reason: '${look.id} at ${size.width}');
      }
    }
  });
}
