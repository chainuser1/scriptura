import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app/theme.dart';
import 'package:scriptures_reader_mobile/app_controller.dart';
import 'package:scriptures_reader_mobile/data/trails/trail_models.dart';
import 'package:scriptures_reader_mobile/data/user/user_store.dart';
import 'package:scriptures_reader_mobile/features/trails/trail_screen.dart';
import 'package:scriptures_reader_mobile/services/engine/search_models.dart';
import 'package:scriptures_reader_mobile/services/engine/search_service.dart';

import '../fakes/fake_search_service.dart';
import 'trail_harness.dart';

Future<(AppController, FakeSearchService)> pumpTrail(WidgetTester tester,
    {Size size = const Size(420, 800), List<List<int>>? batches, SearchService? service, bool reduceMotion = false}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final script = batches ?? [[2, 3, 4], [3, 4, 5], [4, 5, 6], [5, 6, 2]];
  var n = 0;
  final svc = FakeSearchService((r, id) async {
    if (r.op == 'explain') {
      return SearchResponse.fromJson({
        'mode': 'explain',
        'families': [
          {'family': 'S', 'share': 0.4, 'genes': [{'id': 'S01_salvific_divine_initiative', 'a': 0.2, 'b': 0.3}]}
        ],
        'mood_matches': <String>[],
        'shared_terms': ['believeth'],
        'shared_entities': <Map<String, String>>[],
      });
    }
    return batchOf(script[n++ % script.length]);
  });
  final app = AppController.fixed(repository: fixtureRepository(), search: service ?? svc, user: UserStore.memory());
  final trail = app.user.createTrail(name: 'Alpha trail', seed: const TrailSeed.verse(1));
  await tester.pumpWidget(MediaQuery(
    data: MediaQueryData(size: size, disableAnimations: reduceMotion),
    child: MaterialApp(theme: appTheme(Brightness.light), home: TrailScreen(app: app, trail: trail, catalog: testCatalog())),
  ));
  await tester.pumpAndSettle();
  return (app, svc);
}

void main() {
  testWidgets('the first card shows a verse and the actions; Like moves to the next with no dialog', (tester) async {
    final (app, _) = await pumpTrail(tester);
    expect(find.text('Alpha trail'), findsOneWidget);
    expect(find.text('Like'), findsOneWidget);
    expect(find.text('Skip'), findsOneWidget);
    expect(find.text('Less like this'), findsOneWidget);
    expect(find.text('Dislike'), findsNothing);
    final first = app.repository!.getPassage(2).reference;
    expect(find.text(first), findsOneWidget);
    await tester.tap(find.text('Like'));
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsNothing);
    expect(find.text(app.repository!.getPassage(3).reference), findsOneWidget);
    expect(find.textContaining('which you liked'), findsOneWidget);
  });

  testWidgets('keys act on the card: L like, S skip, D less like this', (tester) async {
    final (app, svc) = await pumpTrail(tester);
    await tester.sendKeyEvent(LogicalKeyboardKey.keyL);
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.keyS);
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.keyD);
    await tester.pumpAndSettle();
    final acted = app.user.trails().first;
    final actions = app.user.trailEvents(acted.id).where((e) => e.action != TrailAction.shown).map((e) => e.action).toList();
    expect(actions, [TrailAction.like, TrailAction.skip, TrailAction.dislike]);
    expect(svc.requests.length, greaterThan(3));
  });

  testWidgets('Why this verse opens a sheet with real reasons and the honesty line', (tester) async {
    await pumpTrail(tester);
    await tester.tap(find.text('Why this verse'));
    await tester.pumpAndSettle();
    expect(find.text('Why this verse is here'), findsOneWidget);
    expect(find.textContaining('Shares themes of'), findsOneWidget);
    expect(find.textContaining('believeth'), findsOneWidget);
  });

  testWidgets('without search data the page explains and offers Settings', (tester) async {
    await pumpTrail(tester, service: UnavailableSearchService('Search data is not installed'));
    expect(find.textContaining('Search data is not installed'), findsOneWidget);
    expect(find.text('Open Settings'), findsOneWidget);
    expect(find.text('Like'), findsNothing);
  });

  testWidgets('a trail with nothing left says so and offers to widen', (tester) async {
    await pumpTrail(tester, batches: [[]]);
    expect(find.textContaining('played everything close'), findsOneWidget);
    expect(find.text('Add variety'), findsOneWidget);
  });

  testWidgets('narrow and wide layouts do not overflow; wide opens Why as a side panel', (tester) async {
    await pumpTrail(tester, size: const Size(360, 640));
    expect(tester.takeException(), isNull);
    await pumpTrail(tester, size: const Size(1280, 800));
    await tester.tap(find.text('Why this verse'));
    await tester.pumpAndSettle();
    expect(find.byType(BottomSheet), findsNothing);
    expect(find.text('Why this verse is here'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('every control is labelled and meets the contrast and tap-target guidelines', (tester) async {
    final handle = tester.ensureSemantics();
    await pumpTrail(tester);
    await expectLater(tester, meetsGuideline(textContrastGuideline));
    await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
    await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
    handle.dispose();
  });

  testWidgets('with reduce motion the next card is there on the first frame', (tester) async {
    final (app, _) = await pumpTrail(tester, reduceMotion: true);
    await tester.tap(find.text('Skip'));
    await tester.pump();
    await tester.pump();
    expect(find.text(app.repository!.getPassage(3).reference), findsOneWidget);
  });

  testWidgets('if the engine stops mid-trail the card stays and a one-line notice offers Try again', (tester) async {
    var calls = 0;
    final svc = FakeSearchService((r, id) async {
      calls++;
      if (calls > 1) throw SearchFailure('internal', 'The search engine is restarting.');
      return batchOf([2, 3, 4]);
    });
    final (app, _) = await pumpTrail(tester, service: svc);
    final first = app.repository!.getPassage(2).reference;
    await tester.tap(find.text('Like'));
    await tester.pumpAndSettle();
    expect(find.text(first), findsOneWidget, reason: 'the card stays');
    expect(find.textContaining('The search engine is restarting.'), findsOneWidget);
    expect(find.text('Try again'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('Tune: choosing a mood is applied at once and shown as a chip', (tester) async {
    final (app, svc) = await pumpTrail(tester);
    await tester.tap(find.text('Tune'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilterChip, 'Comfort'));
    await tester.pumpAndSettle();
    expect(app.user.trails().first.moods, ['comfort']);
    expect((svc.requests.last.body!['moods'] as List).length, 1);
  });
}
