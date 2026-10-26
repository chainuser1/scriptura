import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app_controller.dart';
import 'package:scriptures_reader_mobile/data/content/catalog.dart';
import 'package:scriptures_reader_mobile/data/content/content_database.dart';
import 'package:scriptures_reader_mobile/data/content/content_repository.dart';
import 'package:scriptures_reader_mobile/data/user/user_store.dart';
import 'package:scriptures_reader_mobile/features/search/search_screen.dart';
import 'package:scriptures_reader_mobile/services/engine/answer_focus.dart';
import 'package:scriptures_reader_mobile/services/engine/search_models.dart';

import 'fakes/fake_search_service.dart';
import 'widget_test.dart' show typeAndSubmit;

// Expand the small fixture to 100 distinct passages without shipping a database.
class _WideRepository extends ContentRepository {
  _WideRepository(super.content, super.catalog);

  @override
  Passage getPassage(int verseId, {String language = 'english'}) => Passage(
        verseId: verseId,
        text: 'Candidate passage $verseId.',
        reference: 'Alpha Book 1:$verseId',
        shortened: 'Alpha 1:$verseId',
        book: 'Alpha Book',
        bookId: 1,
        chapter: 1,
        verse: verseId,
        language: language,
        requestedLanguage: language,
        source: 'synthetic',
        qualityTier: 'test',
      );

  @override
  List<Passage> getChapter(int bookId, int chapter, {String language = 'english'}) =>
      [for (var i = 1; i <= 100; i++) getPassage(i, language: language)];
}

void main() {
  for (final model in FocusModel.values) {
    for (final k in [10, 15, 30, 60, 100]) {
      testWidgets('${model.name} retrieves and scores $k passages before grouping', (tester) async {
        tester.view.physicalSize = const Size(1280, 800);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.reset);
        final db = ContentDatabase.open('test/fixtures/content_v2_mini.db');
        addTearDown(db.dispose);
        final repo = _WideRepository(db, Catalog.load('test/fixtures/catalog_mini.db', contract: db.contract));
        final service = FakeSearchService((r, id) async {
          if (r.op == 'focus') {
            expect(r.body!['texts'], [for (var i = 1; i <= k; i++) 'Candidate passage $i.']);
            return SearchResponse(mode: 'focus', raw: {
              'scores': [for (var i = 1; i <= k; i++) i.toDouble()],
              'ms': 100.0,
            });
          }
          expect(r.topK, k);
          return semantic(List.generate(r.topK, (i) => i + 1));
        }, hasFocus: true);
        final app = AppController.fixed(repository: repo, search: service, user: UserStore.memory());
        addTearDown(app.dispose);
        app.user.setPref('answer_focus_choice', FocusChoice(model, FocusVariant.int8, 60, 100).toJson());
        app.setFocusLimit(k);
        await tester.pumpWidget(MaterialApp(home: Scaffold(body: SearchScreen(app: app))));
        await typeAndSubmit(tester, find.byType(TextField).first, 'find the strongest answer');
        expect(service.requests.map((r) => r.op), ['search', 'focus']);
        // The strongest verse anchors the card, including candidates beyond the old pool.
        expect(find.byKey(ValueKey('hit-$k')), findsOneWidget);
        expect(find.text('Alpha Book 1:1–$k'), findsNWidgets(2));
        expect(tester.takeException(), isNull);
      });
    }
  }
}
