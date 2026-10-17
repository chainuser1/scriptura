import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app/nav_state.dart';
import 'package:scriptures_reader_mobile/app_controller.dart';
import 'package:scriptures_reader_mobile/data/content/catalog.dart';
import 'package:scriptures_reader_mobile/data/content/content_database.dart';
import 'package:scriptures_reader_mobile/data/content/content_repository.dart';
import 'package:scriptures_reader_mobile/data/trails/trail_models.dart';
import 'package:scriptures_reader_mobile/data/user/user_store.dart';
import 'package:scriptures_reader_mobile/main.dart';
import 'package:scriptures_reader_mobile/services/engine/answer_focus.dart';
import 'package:scriptures_reader_mobile/services/engine/search_models.dart';
import 'package:scriptures_reader_mobile/services/engine/search_service.dart';

import 'fakes/fake_search_service.dart';

ContentRepository fixtureRepository() {
  final db = ContentDatabase.open('test/fixtures/content_v2_mini.db');
  return ContentRepository(db, Catalog.load('test/fixtures/catalog_mini.db', contract: db.contract));
}

Future<AppController> boot(WidgetTester tester, {SearchService? search, Size size = const Size(1280, 800)}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final app = AppController.fixed(repository: fixtureRepository(), search: search, user: UserStore.memory());
  await tester.pumpWidget(ScripturesReaderApp(app: app));
  await tester.pumpAndSettle();
  return app;
}

Future<void> openSection(WidgetTester tester, String label) async {
  await tester.tap(find.descendant(of: find.byType(NavigationRail), matching: find.text(label)));
  await tester.pumpAndSettle();
}

Future<void> typeAndSubmit(WidgetTester tester, Finder field, String text) async {
  await tester.enterText(field, text);
  await tester.testTextInput.receiveAction(TextInputAction.search);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('without content the welcome screen waits for the automatic setup; nothing to choose', (tester) async {
    await tester.pumpWidget(ScripturesReaderApp(app: AppController.fixed()));
    expect(find.text('Welcome'), findsOneWidget);
    expect(find.text('Choose folder…'), findsNothing);
    expect(find.textContaining('Download instead'), findsNothing);
  });

  group('home', () {
    testWidgets('offers the ask box, starter questions and the guide', (tester) async {
      await boot(tester, search: FakeSearchService((r, i) async => semantic([1])));
      expect(find.textContaining('Ask a question'), findsWidgets);
      expect(find.text('What is faith?'), findsOneWidget);
      expect(find.text('Start here'), findsOneWidget);
      await tester.ensureVisible(find.text('Start here')); // below the starter trails on a small window
      await tester.pumpAndSettle();
      await tester.tap(find.text('Start here'));
      await tester.pumpAndSettle();
      expect(find.text('What is in the library'), findsOneWidget);
      expect(find.text('Book of Mormon'), findsOneWidget);
    });

    testWidgets('a starter question becomes a search with results', (tester) async {
      final svc = FakeSearchService((r, i) async => semantic([2, 5]));
      await boot(tester, search: svc);
      await tester.tap(find.text('What is faith?'));
      await tester.pumpAndSettle();
      expect(svc.requests.single.query, 'What is faith?');
      expect(find.text('Alpha Book 1:2'), findsWidgets);
      expect(find.text('Passages for “What is faith?”'), findsOneWidget);
    });

    testWidgets('when search is unavailable, Home says so and still lets you read', (tester) async {
      await boot(tester, search: UnavailableSearchService('The search data is not installed.'));
      expect(find.textContaining('The search data is not installed.'), findsWidgets);
      expect(find.text('Open Settings'), findsOneWidget);
    });
  });

  group('reading', () {
    testWidgets('browse to a chapter and read; the position is remembered', (tester) async {
      final app = await boot(tester, search: FakeSearchService((r, i) async => semantic([1])));
      await openSection(tester, 'Read');
      expect(find.text('Old Testament'), findsOneWidget);
      expect(find.widgetWithText(ChoiceChip, '1'), findsOneWidget); // the first book is open
      await tester.tap(find.widgetWithText(ChoiceChip, '2'));
      await tester.pumpAndSettle();
      expect(find.textContaining('Synthetic English passage 4.'), findsOneWidget);
      expect(app.user.position!.chapter, 2);
    });

    testWidgets('a verse menu bookmarks, and Study lists it', (tester) async {
      final app = await boot(tester, search: FakeSearchService((r, i) async => semantic([1])));
      app.nav.openChapter(1, 1);
      await tester.pumpAndSettle();
      await tester.tap(find.textContaining('Synthetic English passage 2.'));
      await tester.pumpAndSettle();
      expect(find.text('Copy with reference'), findsOneWidget);
      await tester.tap(find.text('Bookmark'));
      await tester.pumpAndSettle();
      expect(app.user.isBookmarked(2), isTrue);
      await openSection(tester, 'Study');
      expect(find.text('Alpha Book 1:2'), findsOneWidget);
    });

    testWidgets('highlight and note from the verse menu are saved', (tester) async {
      final app = await boot(tester, search: FakeSearchService((r, i) async => semantic([1])));
      app.nav.openChapter(1, 1);
      await tester.pumpAndSettle();
      await tester.tap(find.textContaining('Synthetic English passage 3.'));
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('Green'));
      await tester.pumpAndSettle();
      expect(app.user.highlightsIn(1, 8), {3: 1});
      await tester.tap(find.textContaining('Synthetic English passage 3.'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Add note'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField).last, 'a thought');
      await tester.tap(find.text('Save'));
      await tester.pumpAndSettle();
      expect(app.user.notes(verseId: 3).single.text, 'a thought');
    });

    testWidgets('switching language re-renders the text and names', (tester) async {
      final app = await boot(tester, search: FakeSearchService((r, i) async => semantic([1])));
      app.nav.openChapter(1, 1);
      await tester.pumpAndSettle();
      app.setLanguage('spanish');
      await tester.pumpAndSettle();
      expect(find.textContaining('Pasaje sintético 1'), findsOneWidget);
      expect(find.text('Libro Alfa 1'), findsWidgets);
    });

    testWidgets('a second language can sit beside the first', (tester) async {
      final app = await boot(tester, search: FakeSearchService((r, i) async => semantic([1])));
      app.user.setPref('parallel', 'spanish');
      app.nav.openChapter(1, 1);
      await tester.pumpAndSettle();
      expect(find.textContaining('Synthetic English passage 1.'), findsOneWidget);
      expect(find.textContaining('Pasaje sintético 1'), findsOneWidget);
    });
  });

  group('command bar', () {
    testWidgets('Ctrl+K with a reference opens that verse', (tester) async {
      final svc = FakeSearchService((r, i) async => SearchResponse(
          mode: 'reference', reference: ReferenceResult(status: 'ok', book: 'Alpha Book', kind: 'verse', firstVerseId: 3, lastVerseId: 3)));
      final app = await boot(tester, search: svc);
      await tester.sendKeyDownEvent(LogicalKeyboardKey.controlLeft);
      await tester.sendKeyEvent(LogicalKeyboardKey.keyK);
      await tester.sendKeyUpEvent(LogicalKeyboardKey.controlLeft);
      await tester.pumpAndSettle();
      expect(find.text('Enter to go · Esc to close'), findsOneWidget);
      await tester.enterText(find.descendant(of: find.byType(Dialog), matching: find.byType(TextField)), 'Alpha Book 1:3');
      await tester.testTextInput.receiveAction(TextInputAction.go);
      await tester.pumpAndSettle();
      expect(app.nav.dest, Dest.read);
      expect(app.nav.verse, 3);
      expect(svc.requests.single.op, 'reference');
    });

    test('a reference lookup sends the text where the engine reads it', () {
      expect(SearchRequest.reference('Alma 31:1').toJson(1)['text'], 'Alma 31:1'); // engine.rs "reference" reads `text`
    });

    testWidgets('Ctrl+K opens the command bar from anywhere, even with nothing focused, and only once', (tester) async {
      await boot(tester, search: FakeSearchService((r, i) async => semantic([1])));
      FocusManager.instance.primaryFocus?.unfocus();
      await tester.pumpAndSettle();
      for (var i = 0; i < 2; i++) {
        await tester.sendKeyDownEvent(LogicalKeyboardKey.controlLeft);
        await tester.sendKeyEvent(LogicalKeyboardKey.keyK);
        await tester.sendKeyUpEvent(LogicalKeyboardKey.controlLeft);
        await tester.pumpAndSettle();
      }
      expect(find.text('Enter to go · Esc to close'), findsOneWidget);
    });

    testWidgets('Ctrl+Alt+Space from another program brings up the command bar', (tester) async {
      await boot(tester, search: FakeSearchService((r, i) async => semantic([1])));
      await tester.binding.defaultBinaryMessenger.handlePlatformMessage(
          'scriptura/desktop', const StandardMethodCodec().encodeMethodCall(const MethodCall('quickSearch')), (_) {});
      await tester.pumpAndSettle();
      expect(find.text('Enter to go · Esc to close'), findsOneWidget);
    });

    testWidgets('Ctrl+Alt+Space inside the window works too', (tester) async {
      await boot(tester, search: FakeSearchService((r, i) async => semantic([1])));
      await tester.sendKeyDownEvent(LogicalKeyboardKey.controlLeft);
      await tester.sendKeyDownEvent(LogicalKeyboardKey.altLeft);
      await tester.sendKeyEvent(LogicalKeyboardKey.space);
      await tester.sendKeyUpEvent(LogicalKeyboardKey.altLeft);
      await tester.sendKeyUpEvent(LogicalKeyboardKey.controlLeft);
      await tester.pumpAndSettle();
      expect(find.text('Enter to go · Esc to close'), findsOneWidget);
    });

    testWidgets('Settings turns quick search from anywhere off and on, and says when the shortcut is taken', (tester) async {
      final calls = <Object?>[];
      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(const MethodChannel('scriptura/desktop'), (c) async {
        calls.add(c.arguments);
        return {'hotkey': false};
      });
      addTearDown(() => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(const MethodChannel('scriptura/desktop'), null));
      final app = await boot(tester, search: FakeSearchService((r, i) async => semantic([1])));
      expect(calls.first, {'background': true}); // on by default
      app.nav.go(Dest.settings);
      await tester.pumpAndSettle();
      final tile = find.text('Quick search from anywhere');
      await tester.scrollUntilVisible(tile, 300, scrollable: find.byType(Scrollable).last);
      await tester.pumpAndSettle();
      expect(find.textContaining('Another program is using Ctrl+Alt+Space'), findsOneWidget);
      await tester.tap(tile);
      await tester.pumpAndSettle();
      expect(app.user.pref('background'), '0');
      expect(calls.last, {'background': false});
    });

    testWidgets('anything else becomes a question', (tester) async {
      final svc = FakeSearchService((r, i) async {
        if (r.op == 'reference') return SearchResponse(mode: 'reference', reference: ReferenceResult(status: 'not_a_reference'));
        return semantic([4]);
      });
      final app = await boot(tester, search: svc);
      await tester.sendKeyDownEvent(LogicalKeyboardKey.controlLeft);
      await tester.sendKeyEvent(LogicalKeyboardKey.keyK);
      await tester.sendKeyUpEvent(LogicalKeyboardKey.controlLeft);
      await tester.pumpAndSettle();
      await tester.enterText(find.descendant(of: find.byType(Dialog), matching: find.byType(TextField)), 'how do I pray');
      await tester.testTextInput.receiveAction(TextInputAction.go);
      await tester.pumpAndSettle();
      expect(app.nav.dest, Dest.search);
      expect(svc.requests.last.query, 'how do I pray');
    });
  });

  group('search', () {
    Future<AppController> inSearch(WidgetTester tester, SearchService svc) async {
      final app = await boot(tester, search: svc);
      await openSection(tester, 'Search');
      return app;
    }

    group('Answer focus', () {
      // Fixture passages 2, 5, 6 and 7; focus scores put them in the opposite order.
      SearchResponse focused(List<double> scores, {double ms = 400}) => SearchResponse(mode: 'focus', raw: {'scores': scores, 'device': 'cpu', 'ms': ms});

      Future<AppController> withFocus(WidgetTester tester, Future<SearchResponse> Function(SearchRequest r) focus, {int k = 10}) async {
        final svc = FakeSearchService((r, id) async => r.op == 'focus' ? focus(r) : r.op == 'phrase' ? SearchResponse(mode: 'phrase', hits: [Hit(2, 0)], total: 1) : semantic([2, 5, 6, 7]),
            hasFocus: true);
        final app = await inSearch(tester, svc);
        app.user.setPref('answer_focus_choice', FocusChoice(FocusVariant.int8, k, 300).toJson());
        return app;
      }

      double top(WidgetTester tester, int id) => tester.getTopLeft(find.byKey(ValueKey('hit-$id'))).dy;

      testWidgets('reorders the top results by how well they answer, sending their texts in order', (tester) async {
        final sent = <SearchRequest>[];
        await withFocus(tester, (r) async {
          sent.add(r);
          return focused([0.1, 0.2, 0.3, 0.4]);
        });
        await typeAndSubmit(tester, find.byType(TextField).first, 'how can I find peace');
        expect(top(tester, 7), lessThan(top(tester, 6)));
        expect(top(tester, 6), lessThan(top(tester, 5)));
        expect(top(tester, 5), lessThan(top(tester, 2)));
        expect(sent.single.body!['query'], 'how can I find peace');
        expect((sent.single.body!['texts'] as List), hasLength(4));
        expect((sent.single.body!['texts'] as List).first, contains('Synthetic English passage'));
      });

      testWidgets('only the top K are reordered', (tester) async {
        final sent = <SearchRequest>[];
        await withFocus(tester, (r) async {
          sent.add(r);
          return focused([0.1, 0.9]);
        }, k: 2);
        await typeAndSubmit(tester, find.byType(TextField).first, 'peace');
        expect((sent.single.body!['texts'] as List), hasLength(2));
        expect(top(tester, 5), lessThan(top(tester, 2)));
        expect(top(tester, 2), lessThan(top(tester, 6)));
        expect(top(tester, 6), lessThan(top(tester, 7)));
      });

      testWidgets('a failure shows today\'s order', (tester) async {
        await withFocus(tester, (r) async => throw SearchFailure('focus_failed', 'driver error'));
        await typeAndSubmit(tester, find.byType(TextField).first, 'peace');
        expect(top(tester, 2), lessThan(top(tester, 7)));
        expect(find.textContaining('driver error'), findsNothing);
      });

      testWidgets('too slow shows today\'s order instead of waiting', (tester) async {
        await withFocus(tester, (r) => Completer<SearchResponse>().future);
        await tester.enterText(find.byType(TextField).first, 'peace');
        await tester.testTextInput.receiveAction(TextInputAction.search);
        await tester.pump(const Duration(seconds: 4));
        await tester.pumpAndSettle();
        expect(find.byKey(const ValueKey('hit-2')), findsOneWidget);
        expect(top(tester, 2), lessThan(top(tester, 7)));
      });

      testWidgets('a newer search wins over an older one still being focused', (tester) async {
        final slow = Completer<SearchResponse>();
        late AppController app;
        final svc = FakeSearchService((r, id) async {
          if (r.op == 'focus') return r.body!['query'] == 'first' ? slow.future : focused([0.1, 0.2, 0.3, 0.4]);
          return r.query == 'first' ? semantic([3]) : semantic([2, 5, 6, 7]);
        }, hasFocus: true);
        app = await inSearch(tester, svc);
        app.user.setPref('answer_focus_choice', const FocusChoice(FocusVariant.int8, 10, 300).toJson());
        await tester.enterText(find.byType(TextField).first, 'first');
        await tester.testTextInput.receiveAction(TextInputAction.search);
        await tester.pump();
        await typeAndSubmit(tester, find.byType(TextField).first, 'second');
        slow.complete(focused([5.0]));
        await tester.pumpAndSettle();
        expect(find.byKey(const ValueKey('hit-3')), findsNothing);
        expect(top(tester, 7), lessThan(top(tester, 2)));
      });

      testWidgets('exact-phrase results are never focused', (tester) async {
        final sent = <SearchRequest>[];
        await withFocus(tester, (r) async {
          sent.add(r);
          return focused([0.1]);
        });
        await tester.tap(find.text('Exact phrase'));
        await tester.pumpAndSettle();
        await typeAndSubmit(tester, find.byType(TextField).first, 'in the beginning');
        expect(sent, isEmpty);
      });

      testWidgets('without the pack, search is exactly today\'s', (tester) async {
        final svc = FakeSearchService((r, id) async => semantic([2, 5, 6, 7]));
        final app = await inSearch(tester, svc);
        app.user.setPref('answer_focus_choice', const FocusChoice(FocusVariant.int8, 10, 300).toJson());
        await typeAndSubmit(tester, find.byType(TextField).first, 'peace');
        expect(svc.requests.map((r) => r.op), ['search']);
        expect(top(tester, 2), lessThan(top(tester, 7)));
      });

      testWidgets('the question trail starts from the focused top three', (tester) async {
        final app = await withFocus(tester, (r) async => focused([0.1, 0.2, 0.3, 0.4]));
        await typeAndSubmit(tester, find.byType(TextField).first, 'how can I find peace');
        await tester.tap(find.text('Start a trail from this question'));
        await tester.pumpAndSettle();
        expect(app.user.trailSeeds(app.user.pref('active_trail')!).map((s) => s.verseId), [7, 6, 5]);
      });

      testWidgets('slow searches teach Automatic to look at fewer candidates', (tester) async {
        final app = await withFocus(tester, (r) async => focused([0.1, 0.2, 0.3, 0.4], ms: 2600), k: 30);
        for (final q in ['one', 'two', 'three']) {
          await typeAndSubmit(tester, find.byType(TextField).first, q);
        }
        expect(app.focusChoice!.k, 15);
      });
    });

    testWidgets('a question starts a trail seeded with the question and its top answers', (tester) async {
      final app = await inSearch(tester, FakeSearchService((r, id) async => semantic([2, 5, 6, 7])));
      await typeAndSubmit(tester, find.byType(TextField).first, 'how can I find peace');
      await tester.tap(find.text('Start a trail from this question'));
      await tester.pumpAndSettle();
      final id = app.user.pref('active_trail')!;
      final trail = app.user.trail(id)!;
      expect(trail.seed.kind, TrailSeedKind.question);
      expect(trail.seed.text, 'how can I find peace');
      expect(app.user.trailSeeds(id).map((s) => s.verseId), [2, 5, 6]); // the top three answers, in order
    });

    testWidgets('exact-phrase results do not offer a question trail', (tester) async {
      await inSearch(tester, FakeSearchService((r, id) async => SearchResponse(mode: 'phrase', hits: [Hit(2, 0)], total: 1)));
      await tester.tap(find.text('Exact phrase'));
      await tester.pumpAndSettle();
      await typeAndSubmit(tester, find.byType(TextField).first, 'in the beginning');
      expect(find.text('Start a trail from this question'), findsNothing);
    });

    testWidgets('results show reference and text with a live preview beside them', (tester) async {
      await inSearch(tester, FakeSearchService((r, id) async => semantic([2, 5])));
      await typeAndSubmit(tester, find.byType(TextField).first, 'faith');
      expect(find.text('Alpha Book 1:2'), findsWidgets);
      expect(find.text('Read the chapter'), findsOneWidget); // preview pane
      await tester.tap(find.byKey(const ValueKey('hit-5')));
      await tester.pumpAndSettle();
      expect(find.text('Alpha Book 2:2'), findsWidgets);
    });

    testWidgets('the search style chosen in Settings is sent with the next search', (tester) async {
      final svc = FakeSearchService((r, id) async => semantic([2]));
      final app = await boot(tester, search: svc);
      await openSection(tester, 'Search');
      await typeAndSubmit(tester, find.byType(TextField).first, 'faith');
      expect(svc.requests.last.profile, isNull, reason: 'the default (Compass) leaves the choice to the engine');

      await openSection(tester, 'Settings');
      await tester.dragUntilVisible(find.text('Search style'), find.byType(ListView).first, const Offset(0, -300));
      await tester.tap(find.text('Search style'));
      await tester.pumpAndSettle();
      await tester.dragUntilVisible(find.text('Tide'), find.byType(ListView).first, const Offset(0, -200));
      await tester.tap(find.text('Tide'));
      await tester.pumpAndSettle();
      expect(app.searchProfile, 'tide');

      await openSection(tester, 'Search');
      await typeAndSubmit(tester, find.byType(TextField).first, 'hope');
      expect(svc.requests.last.profile, 'tide');
    });

    testWidgets('exact phrase mode sends a phrase request and reports the total', (tester) async {
      final svc = FakeSearchService((r, id) async => SearchResponse(mode: 'phrase', hits: [Hit(1, 0), Hit(3, 0)], total: 2));
      await inSearch(tester, svc);
      await tester.tap(find.text('Exact phrase'));
      await tester.pump();
      await typeAndSubmit(tester, find.byType(TextField).first, 'english passage');
      expect(svc.requests.single.op, 'phrase');
      expect(find.textContaining('2 verses contain'), findsOneWidget);
    });

    testWidgets('a reference result offers to open the passage', (tester) async {
      final svc = FakeSearchService((r, id) async => SearchResponse(
          mode: 'reference', reference: ReferenceResult(status: 'ok', book: 'Alpha Book', kind: 'verse', firstVerseId: 3, lastVerseId: 3)));
      await inSearch(tester, svc);
      await typeAndSubmit(tester, find.byType(TextField).first, 'Alpha Book 1:3');
      expect(find.text('Open Alpha Book 1:3'), findsOneWidget);
    });

    testWidgets('an out-of-range reference says why', (tester) async {
      final svc = FakeSearchService((r, id) async => SearchResponse(
          mode: 'reference', reference: ReferenceResult(status: 'out_of_range', reason: 'Alpha Book has 2 chapters, not 9')));
      await inSearch(tester, svc);
      await typeAndSubmit(tester, find.byType(TextField).first, 'Alpha Book 9');
      expect(find.text('Alpha Book has 2 chapters, not 9'), findsOneWidget);
    });

    testWidgets('an ambiguous person shows one chip per candidate and re-runs with the chosen person', (tester) async {
      final svc = FakeSearchService((r, id) async {
        final amb = r.person == null;
        return semantic([1, 2],
            person: PersonInterpretation(
                amb ? 'ambiguous' : 'single',
                [PersonChip('person:a', 'Moroni', 'captain', !amb), PersonChip('person:b', 'Moroni', 'son of Mormon', false)],
                !amb));
      });
      await inSearch(tester, svc);
      await typeAndSubmit(tester, find.byType(TextField).first, 'Who is Moroni?');
      expect(find.text('Several people or places share this name. Which one?'), findsOneWidget);
      await tester.tap(find.text('Moroni · son of Mormon'));
      await tester.pumpAndSettle();
      expect(svc.requests.last.person, 'person:b');
      expect(find.text('Showing passages about the person you named.'), findsOneWidget);
    });

    testWidgets('a fallback profile is disclosed', (tester) async {
      await inSearch(tester, FakeSearchService((r, id) async => semantic([1], profile: 'lantern', requested: 'compass'), colbert: false));
      await typeAndSubmit(tester, find.byType(TextField).first, 'faith');
      expect(find.textContaining('lantern search profile'), findsOneWidget);
    });

    testWidgets('a newer request wins; the older response is ignored and the older request cancelled', (tester) async {
      final first = Completer<SearchResponse>();
      final svc = FakeSearchService((r, id) => r.query == 'first' ? first.future : Future.value(semantic([4])));
      await inSearch(tester, svc);
      final field = find.byType(TextField).first;
      await tester.enterText(field, 'first');
      await tester.testTextInput.receiveAction(TextInputAction.search);
      await tester.pump();
      await tester.enterText(field, 'second');
      await tester.testTextInput.receiveAction(TextInputAction.search);
      await tester.pumpAndSettle();
      expect(svc.cancelled, hasLength(1));
      first.complete(semantic([1]));
      await tester.pumpAndSettle();
      expect(find.text('Alpha Book 2:1'), findsWidgets);
      expect(find.text('Alpha Book 1:1'), findsNothing);
    });

    testWidgets('cancelling shows a cancelled note and keeps the screen usable', (tester) async {
      await inSearch(tester, FakeSearchService((r, id) => Future.error(SearchFailure('cancelled', 'request cancelled'))));
      await typeAndSubmit(tester, find.byType(TextField).first, 'faith');
      expect(find.text('Search cancelled.'), findsOneWidget);
    });

    testWidgets('engine errors are shown with their reason', (tester) async {
      await inSearch(tester, FakeSearchService((r, id) => Future.error(SearchFailure('inference_failure', 'model file is corrupt'))));
      await typeAndSubmit(tester, find.byType(TextField).first, 'faith');
      expect(find.textContaining('model file is corrupt'), findsOneWidget);
    });

    testWidgets('similar verses from a result run a similar request', (tester) async {
      final svc = FakeSearchService((r, id) async => r.op == 'similar' ? semantic([6, 7]) : semantic([2]));
      await inSearch(tester, svc);
      await typeAndSubmit(tester, find.byType(TextField).first, 'faith');
      await tester.tap(find.byTooltip('More').first);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Similar verses').last);
      await tester.pumpAndSettle();
      expect(svc.requests.last.op, 'similar');
      expect(svc.requests.last.verseId, 2);
    });
  });

  testWidgets('the narrow layout uses a bottom bar and nothing overflows', (tester) async {
    await boot(tester, search: FakeSearchService((r, i) async => semantic([1])), size: const Size(420, 760));
    expect(find.byType(NavigationBar), findsOneWidget);
    await tester.tap(find.descendant(of: find.byType(NavigationBar), matching: find.text('Read')));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });
}
