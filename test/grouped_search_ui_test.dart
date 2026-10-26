import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app/nav_state.dart';
import 'package:scriptures_reader_mobile/app/passage_navigation.dart';
import 'package:scriptures_reader_mobile/services/engine/answer_focus.dart';
import 'package:scriptures_reader_mobile/services/engine/search_models.dart';
import 'fakes/fake_search_service.dart';
import 'widget_test.dart' show boot, typeAndSubmit;

void main() {
  testWidgets(
      'desktop preview retains gaps, jumps passages and copies the complete group',
      (tester) async {
    final svc = FakeSearchService((r, id) async => semantic([3, 6, 1]));
    final app = await boot(tester, search: svc);
    addTearDown(app.dispose);
    app.nav.go(Dest.search);
    await tester.pumpAndSettle();
    await typeAndSubmit(tester, find.byType(TextField).first, 'trust');
    expect(find.text('Alpha Book 1:1, 3'), findsNWidgets(2));
    expect(find.byKey(const ValueKey('hit-1')), findsNothing);
    final preview = find.byKey(const ValueKey('passage-preview'));
    expect(
        find.descendant(
            of: preview,
            matching: find.textContaining('Synthetic English passage 2.')),
        findsOneWidget,
        reason: 'unmatched context remains readable');
    await tester.tap(find.descendant(
        of: find.byType(PassageNavigation).last, matching: find.text('1')));
    await tester.pumpAndSettle();
    expect(find.text('Passage 1 of 2'), findsOneWidget);
    String? copied;
    tester.binding.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, (call) async {
      if (call.method == 'Clipboard.setData') {
        copied = (call.arguments as Map)['text'] as String;
      }
      return null;
    });
    addTearDown(() => tester.binding.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, null));
    await tester.tap(find.byTooltip('Copy matched passages'));
    await tester.pumpAndSettle();
    expect(copied, contains('Alpha Book 1:1'));
    expect(copied, contains('Alpha Book 1:3'));
    expect(copied, isNot(contains('Synthetic English passage 2.')));
    await tester.tap(find.text('Read the chapter'));
    await tester.pumpAndSettle();
    expect(app.nav.verse, 1);
    expect(app.nav.searchSelection!.passages.map((p) => p.verseId), [1, 3]);
    await tester.tap(find.byTooltip('Next passage'));
    await tester.pumpAndSettle();
    expect(app.nav.verse, 3);
    await tester.tap(find.text('Back to results'));
    await tester.pumpAndSettle();
    expect(find.text('Passage 2 of 2'), findsOneWidget);
    expect(svc.requests, hasLength(1),
        reason: 'exploring groups makes no model calls');
    expect(tester.takeException(), isNull);
  });

  testWidgets(
      'phone opens the whole range at its start and preserves saved highlights',
      (tester) async {
    final semantics = tester.ensureSemantics();

    final app = await boot(tester,
        size: const Size(390, 800),
        search: FakeSearchService((r, id) async => semantic([3, 1, 2])));
    addTearDown(app.dispose);
    app.nav.go(Dest.search);
    await tester.pumpAndSettle();
    await typeAndSubmit(tester, find.byType(TextField).first, 'trust');
    app.user.toggleHighlight(2, 1);
    app.user.toggleBookmark(3);
    await tester.tap(find.byKey(const ValueKey('hit-3')));
    await tester.pumpAndSettle();
    expect(app.nav.dest, Dest.read);
    expect(app.user.highlightsIn(1, 3), {2: 1});
    expect(
        find.bySemanticsLabel(
            'Verse 2, search match, active passage, highlighted'),
        findsOneWidget);
    expect(
        find.bySemanticsLabel(
            'Verse 3, search match, active passage, bookmarked'),
        findsOneWidget);
    expect(app.nav.verse, 1, reason: 'rank anchor 3 opens at start of 1-3');
    expect(app.nav.searchSelection!.passages.map((p) => p.verseId), [1, 2, 3]);
    expect(find.text('Alpha Book 1:1–3'), findsOneWidget);
    await tester.tap(find.text('Back to results'));
    await tester.pumpAndSettle();
    await typeAndSubmit(tester, find.byType(TextField).first, 'a new query');
    expect(app.nav.searchSelection, isNull);
    expect(tester.takeException(), isNull);
    semantics.dispose();
  });

  testWidgets(
      'group display is reversible without losing matches or expansion state',
      (tester) async {
    final app = await boot(tester,
        search: FakeSearchService((r, id) async => semantic([3, 1, 6])));
    addTearDown(app.dispose);
    app.nav.go(Dest.search);
    await tester.pumpAndSettle();
    await typeAndSubmit(tester, find.byType(TextField).first, 'trust');
    await tester.tap(find.text('Expand passages'));
    await tester.pumpAndSettle();
    expect(find.text('Collapse passages'), findsOneWidget);
    await tester.tap(find.byTooltip('Result display'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(
        CheckedPopupMenuItem<bool>, 'Show matches separately'));
    await tester.pumpAndSettle();
    for (final id in [3, 1, 6]) {
      expect(find.byKey(ValueKey('hit-$id')), findsOneWidget);
    }
    await tester.tap(find.byTooltip('Result display'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(
        CheckedPopupMenuItem<bool>, 'Group related passages'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('hit-1')), findsNothing);
    expect(find.text('Collapse passages'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('after reranking all chapter matches share one card',
      (tester) async {
    final svc = FakeSearchService(
        (r, id) async => r.op == 'focus'
            ? SearchResponse(mode: 'focus', raw: {
                'scores': [0.8, 0.9, 0.1],
                'ms': 10.0
              })
            : semantic([1, 6, 3]),
        hasFocus: true);
    final app = await boot(tester, search: svc);
    addTearDown(app.dispose);
    app.user.setPref('answer_focus_choice',
        const FocusChoice(FocusModel.ezra, FocusVariant.int8, 2, 300).toJson());
    app.nav.go(Dest.search);
    await tester.pumpAndSettle();
    await typeAndSubmit(tester, find.byType(TextField).first, 'trust');
    for (final id in [6, 1]) {
      expect(find.byKey(ValueKey('hit-$id')), findsOneWidget);
    }
    expect(find.byKey(const ValueKey('hit-3')), findsNothing);
    expect(find.text('Alpha Book 1:1, 3'), findsOneWidget);
    expect(tester.getTopLeft(find.byKey(const ValueKey('hit-6'))).dy,
        lessThan(tester.getTopLeft(find.byKey(const ValueKey('hit-1'))).dy));
    expect(svc.requests.map((r) => r.op), ['search', 'focus']);
  });
  testWidgets(
      'Answer Focus selects the strongest passage by default within its chapter card',
      (tester) async {
    final svc = FakeSearchService(
        (r, id) async => r.op == 'focus'
            ? SearchResponse(mode: 'focus', raw: {
                'scores': [0.1, 0.2, 0.9, 0.3],
                'ms': 10.0
              })
            : semantic([1, 6, 3, 4]),
        hasFocus: true);
    final app = await boot(tester, search: svc);
    addTearDown(app.dispose);
    app.user.setPref(
        'answer_focus_choice',
        const FocusChoice(FocusModel.ezra, FocusVariant.int8, 10, 300)
            .toJson());
    app.nav.go(Dest.search);
    await tester.pumpAndSettle();
    await typeAndSubmit(tester, find.byType(TextField).first, 'trust');
    expect(find.byKey(const ValueKey('hit-1')), findsNothing);
    for (final id in [3, 4, 6]) {
      expect(find.byKey(ValueKey('hit-$id')), findsOneWidget);
    }
    final navigation = find.byType(PassageNavigation).last;
    Iterable<bool> checks() => tester
        .widgetList<ChoiceChip>(
            find.descendant(of: navigation, matching: find.byType(ChoiceChip)))
        .map((c) => c.selected);
    expect(checks(), [false, true],
        reason: 'verse 3 has the highest Answer Focus score');
    await tester.tap(find.descendant(of: navigation, matching: find.text('1')));
    await tester.pumpAndSettle();
    expect(checks(), [true, false]);
    await tester.tap(find.text('Read the chapter'));
    await tester.pumpAndSettle();
    expect(app.nav.verse, 1);
    expect(app.nav.searchSelection!.anchor.verseId, 3);
    expect(app.nav.searchSelection!.passages.map((p) => p.verseId), [1, 3]);
    expect(svc.requests.map((r) => r.op), ['search', 'focus']);
  });

  testWidgets(
      'manual reader scroll and result position survive navigation and preference rebuilds',
      (tester) async {
    final app = await boot(tester,
        size: const Size(390, 600),
        search:
            FakeSearchService((r, id) async => semantic([3, 1, 8, 6, 4, 5])));
    addTearDown(app.dispose);
    app.nav.go(Dest.search);
    await tester.pumpAndSettle();
    await typeAndSubmit(tester, find.byType(TextField).first, 'trust');
    await tester.ensureVisible(find.text('Expand passages').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Expand passages').first);
    await tester.pumpAndSettle();
    final results = find.byKey(const ValueKey('search-results'));
    final resultScroll = tester
        .state<ScrollableState>(find
            .descendant(of: results, matching: find.byType(Scrollable))
            .first)
        .position;
    final secondTitle = find
        .descendant(
            of: find.byKey(const ValueKey('hit-8')),
            matching: find.byType(Text))
        .first;
    await tester.ensureVisible(secondTitle);
    await tester.pumpAndSettle();
    final before = resultScroll.pixels;
    expect(before, greaterThan(0));
    await tester.tap(secondTitle);
    await tester.pumpAndSettle();
    app.user.setPref('text_scale', '1.8');
    await tester.pumpAndSettle();
    final readerScroll = find
        .byType(Scrollable)
        .evaluate()
        .map((e) => (e as StatefulElement).state as ScrollableState)
        .firstWhere((s) => s.position.axis == Axis.vertical)
        .position;
    readerScroll.jumpTo(0);
    await tester.pumpAndSettle();
    app.user.toggleHighlight(1, 0);
    await tester.pumpAndSettle();
    expect(readerScroll.pixels, 0,
        reason: 'a saved highlight must not snap back to the match');
    await tester.tap(find.text('Back to results'));
    await tester.pumpAndSettle();
    expect(resultScroll.pixels, before);
    resultScroll.jumpTo(0);
    await tester.pumpAndSettle();
    expect(find.text('Collapse passages'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('group toggles cannot restore stale reader collections',
      (tester) async {
    final app = await boot(tester,
        search: FakeSearchService((r, id) async => semantic([3, 1])));
    addTearDown(app.dispose);
    app.nav.go(Dest.search);
    await tester.pumpAndSettle();
    await typeAndSubmit(tester, find.byType(TextField).first, 'trust');
    await tester.tap(find.text('Read the chapter'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Back to results'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Result display'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(
        CheckedPopupMenuItem<bool>, 'Show matches separately'));
    await tester.pumpAndSettle();
    app.nav.go(Dest.settings);
    await tester.pumpAndSettle();
    app.nav.go(Dest.search);
    await tester.pumpAndSettle();
    expect(find.text('Alpha Book 1:1, 3'), findsNothing);
    await tester.tap(find.text('Read the chapter'));
    await tester.pumpAndSettle();
    expect(app.nav.searchSelection!.passages.map((p) => p.verseId), [3]);
    app.nav.openChapter(1, 2);
    await tester.pumpAndSettle();
    expect(app.nav.searchSelection, isNull);
    expect(find.text('Back to results'), findsNothing);
  });

  testWidgets(
      'discontinuous groups remain usable with large text and reading themes on a phone',
      (tester) async {
    final app = await boot(tester,
        size: const Size(360, 640),
        search: FakeSearchService((r, id) async => semantic([3, 1])));
    addTearDown(app.dispose);
    app.user.setPref('text_scale', '1.8');
    app.nav.go(Dest.search);
    await tester.pumpAndSettle();
    await typeAndSubmit(tester, find.byType(TextField).first, 'trust');
    await tester.tap(find.byKey(const ValueKey('hit-3')));
    await tester.pumpAndSettle();
    for (final theme in ['paper', 'sepia', 'night', 'contrast']) {
      app.user.setPref('reading_theme', theme);
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('Previous passage'));
      await tester.pumpAndSettle();
      expect(app.nav.verse, 1);
      await tester.tap(find.byTooltip('Next passage'));
      await tester.pumpAndSettle();
      expect(app.nav.verse, 3);
      expect(tester.takeException(), isNull, reason: theme);
    }
  });
}
