import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app/theme.dart';
import 'package:scriptures_reader_mobile/app_controller.dart';
import 'package:scriptures_reader_mobile/data/content/catalog.dart';
import 'package:scriptures_reader_mobile/data/trails/trail_models.dart';
import 'package:scriptures_reader_mobile/data/user/user_store.dart';
import 'package:scriptures_reader_mobile/features/trails/taste_screen.dart';
import 'package:scriptures_reader_mobile/features/trails/taste_summary.dart';
import 'package:scriptures_reader_mobile/services/engine/search_models.dart';

import '../fakes/fake_search_service.dart';
import 'trail_harness.dart';

void main() {
  test('the sentence names the leaning families and the volume, and is honest when there is little', () {
    expect(tasteSentence(familyLabels: ['Salvation', 'Divine reference'], volumeName: 'the Book of Mormon'),
        'You lean toward salvation and divine reference, mostly in the Book of Mormon.');
    expect(tasteSentence(familyLabels: ['Emotion'], volumeName: null), 'You lean toward emotion.');
    expect(tasteSentence(familyLabels: const [], volumeName: null), 'Like a few verses on a trail and your taste will show here.');
  });

  test('volume shares are the fractions of liked verses per volume, largest first', () {
    final vols = [VolumeEntry(1, 'ot', 'Old Testament', null, 'x', 1, 100), VolumeEntry(2, 'bom', 'Book of Mormon', null, 'x', 101, 200)];
    final s = volumeShares([5, 150, 160, 170], vols);
    expect(s.first.name, 'Book of Mormon');
    expect(s.first.share, closeTo(0.75, 1e-9));
  });

  test('clearing feedback is undoable and leaves shown and skip events alone', () {
    final s = UserStore.memory();
    final t = s.createTrail(name: 'T', seed: const TrailSeed.verse(1));
    s.addTrailEvent(t.id, 2, TrailAction.shown);
    s.addTrailEvent(t.id, 2, TrailAction.like);
    s.addTrailEvent(t.id, 3, TrailAction.skip);
    final rows = s.clearFeedback();
    expect(s.likeDislikeEvents(), isEmpty);
    expect(s.trailEvents(t.id).map((e) => e.action), [TrailAction.shown, TrailAction.skip]);
    s.restoreFeedback(rows);
    expect(s.likeDislikeEvents().length, 1);
    s.dispose();
  });

  testWidgets('the taste screen shows leanings from the engine, an empty state, and Reset with Undo', (tester) async {
    tester.view.physicalSize = const Size(900, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final svc = FakeSearchService((r, id) async => SearchResponse.fromJson({
          'mode': 'taste',
          'families': [{'family': 'S', 'score': 0.9}, {'family': 'F', 'score': 0.4}]
        }));
    final app = AppController.fixed(repository: fixtureRepository(), search: svc, user: UserStore.memory());
    await tester.pumpWidget(MaterialApp(theme: appTheme(Brightness.light), home: TasteScreen(app: app, catalog: testCatalog())));
    await tester.pumpAndSettle();
    expect(find.textContaining('Like a few verses'), findsOneWidget);

    final t = app.user.createTrail(name: 'T', seed: const TrailSeed.verse(1));
    app.user.addTrailEvent(t.id, 2, TrailAction.like);
    await tester.pumpWidget(MaterialApp(theme: appTheme(Brightness.light), home: TasteScreen(app: app, catalog: testCatalog())));
    await tester.pumpAndSettle();
    expect(find.textContaining('You lean toward'), findsOneWidget);
    await tester.tap(find.text('Reset'));
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsNothing);
    expect(app.user.likeDislikeEvents(), isEmpty);
    await tester.tap(find.text('Undo'));
    await tester.pumpAndSettle();
    expect(app.user.likeDislikeEvents().length, 1);
  });
}
