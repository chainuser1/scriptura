import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app_controller.dart';
import 'package:scriptures_reader_mobile/data/trails/trail_models.dart';
import 'package:scriptures_reader_mobile/data/user/user_store.dart';
import 'package:scriptures_reader_mobile/features/trails/trail_controller.dart';
import 'package:scriptures_reader_mobile/services/engine/search_models.dart';
import 'package:scriptures_reader_mobile/services/engine/search_service.dart';

import '../fakes/fake_search_service.dart';
import 'trail_harness.dart';

void main() {
  late FakeSearchService svc;
  late List<List<int>> script; // batches handed out in order
  late AppController app;

  Future<TrailController> open({List<List<int>>? batches}) async {
    script = batches ?? [[2, 3, 4, 5, 6], [3, 4, 5, 6, 2], [4, 5, 6, 2, 3], [5, 6, 2, 3, 4]];
    var n = 0;
    svc = FakeSearchService((r, id) async => batchOf(script[n++ % script.length]));
    app = AppController.fixed(repository: fixtureRepository(), search: svc, user: UserStore.memory());
    final trail = app.user.createTrail(name: 'Alpha', seed: const TrailSeed.verse(1));
    final c = TrailController(app: app, trail: trail, catalog: testCatalog());
    await c.start();
    return c;
  }

  test('start asks for a batch from the seed, shows the first verse and records it as shown', () async {
    final c = await open();
    expect(c.phase, TrailPhase.ready);
    expect(c.current, 2);
    final body = svc.requests.first.body!;
    expect(body['op'], 'trail_next');
    expect(body['seed'], {'verse_id': 1});
    expect(body['events'], isEmpty);
    expect(app.user.trailEvents(c.trail.id).map((e) => e.action), [TrailAction.shown]);
  });

  test('a like is recorded, replayed to the engine and the next verse is a different one', () async {
    final c = await open();
    await c.feedback(TrailAction.like);
    expect(c.current, 3);
    final events = app.user.trailEvents(c.trail.id).map((e) => (e.verseId, e.action)).toList();
    expect(events, [(2, TrailAction.shown), (2, TrailAction.like), (3, TrailAction.shown)]);
    final body = svc.requests.last.body!;
    expect((body['events'] as List).map((e) => e['action']), ['shown', 'like']);
    expect(body['recent'], [2]);
    expect(c.reasonHint, contains('liked'));
  });

  test('rapid feedback applies in order, once each, and never repeats a card', () async {
    final c = await open(batches: [[2, 3, 4, 5, 6], [3, 4, 5, 6], [4, 5, 6], [5, 6]]);
    final fs = [c.feedback(TrailAction.like), c.feedback(TrailAction.skip), c.feedback(TrailAction.dislike)];
    await Future.wait(fs);
    final acted = app.user.trailEvents(c.trail.id).where((e) => e.action != TrailAction.shown).map((e) => (e.verseId, e.action)).toList();
    expect(acted, [(2, TrailAction.like), (3, TrailAction.skip), (4, TrailAction.dislike)]);
    final shown = app.user.trailEvents(c.trail.id).where((e) => e.action == TrailAction.shown).map((e) => e.verseId).toList();
    expect(shown.toSet().length, shown.length);
  });

  test('a verse the content pack cannot render is recorded as shown and skipped silently', () async {
    final c = await open(batches: [[999999, 3, 4]]);
    expect(c.current, 3);
    final shown = app.user.trailEvents(c.trail.id).where((e) => e.action == TrailAction.shown).map((e) => e.verseId).toList();
    expect(shown, [999999, 3]);
    expect(app.user.trailEvents(c.trail.id).where((e) => e.action == TrailAction.skip), isEmpty);
  });

  test('an empty batch is the empty state, not a crash', () async {
    final c = await open(batches: [[]]);
    expect(c.phase, TrailPhase.empty);
    expect(c.current, isNull);
  });

  test('with no engine the card area explains instead of failing', () async {
    app = AppController.fixed(repository: fixtureRepository(), search: UnavailableSearchService('Search data is not installed'), user: UserStore.memory());
    final trail = app.user.createTrail(name: 'Alpha', seed: const TrailSeed.verse(1));
    final c = TrailController(app: app, trail: trail, catalog: testCatalog());
    await c.start();
    expect(c.phase, TrailPhase.engineDown);
  });

  test('tuning sends the moods genes and focus on the next request and keeps the current card', () async {
    final c = await open();
    final before = c.current;
    await c.tune(moods: ['comfort'], focus: 0.9, moodStrength: 0.8, volume: 'bom');
    final body = svc.requests.last.body!;
    expect(body['moods'], [
      [{'id': 'D18_emotion_comfort_consolation', 'weight': 1.0}]
    ]);
    expect(body['focus'], 0.9);
    expect(body['mood_strength'], 0.8);
    expect(body.containsKey('filter'), isTrue); // the range itself comes from the catalog's volumes (covered in the engine tests)
    expect(c.current, before);
    expect(app.user.trail(c.trail.id)!.moods, ['comfort']);
    expect(app.user.trail(c.trail.id)!.volume, 'bom');
  });

  test('when the engine fails mid-trail the card stays, the problem is kept, and Try again continues', () async {
    var calls = 0;
    var fail = false;
    app = AppController.fixed(
      repository: fixtureRepository(),
      search: FakeSearchService((r, id) async {
        calls++;
        if (fail) throw SearchFailure('internal', 'the search engine is restarting');
        return batchOf([2, 3, 4]);
      }),
      user: UserStore.memory(),
    );
    final trail = app.user.createTrail(name: 'Alpha', seed: const TrailSeed.verse(1));
    final c = TrailController(app: app, trail: trail, catalog: testCatalog());
    await c.start();
    expect(c.current, 2);
    fail = true;
    await c.feedback(TrailAction.like);
    expect(c.current, 2, reason: 'the card stays');
    expect(c.phase, TrailPhase.ready);
    expect(c.problem, contains('restarting'));
    fail = false;
    await c.retry();
    expect(c.problem, isNull);
    expect(c.current, 3, reason: 'the like was already recorded; retry moves on and does not record it twice');
    expect(app.user.trailEvents(c.trail.id).where((e) => e.action == TrailAction.like).length, 1);
    expect(calls, greaterThan(2));
  });

  test('reopening resumes on the card that was showing', () async {
    final c = await open();
    await c.feedback(TrailAction.skip);
    final shownNow = c.current;
    final again = TrailController(app: app, trail: app.user.trail(c.trail.id)!, catalog: testCatalog());
    await again.start();
    expect(again.current, shownNow);
  });
}
