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

void main() {
  testWidgets('a new search shows its results from the top, not where the last list was scrolled to', (tester) async {
    tester.view.physicalSize = const Size(360, 420);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final svc = FakeSearchService((r, i) async => semantic([1, 2, 3, 4, 5, 6, 7, 8]));
    final app = AppController.fixed(repository: fixtureRepository(), search: svc, user: UserStore.memory());
    await tester.pumpWidget(ScripturesReaderApp(app: app));
    await tester.pumpAndSettle();
    app.nav.go(Dest.search);
    await tester.pumpAndSettle();

    Future<void> ask(String q) async {
      await tester.enterText(find.byType(TextField).first, q);
      await tester.testTextInput.receiveAction(TextInputAction.search);
      await tester.pumpAndSettle();
    }

    double offset() => tester.state<ScrollableState>(find.descendant(of: find.byKey(const ValueKey('search-results')), matching: find.byType(Scrollable))).position.pixels;

    await ask('What is faith?');
    await tester.drag(find.byKey(const ValueKey('search-results')), const Offset(0, -300));
    await tester.pumpAndSettle();
    expect(offset(), greaterThan(0), reason: 'the first list was scrolled down');
    await ask('How do I pray?');
    expect(offset(), 0, reason: 'a new search starts at the top');
  });
}
