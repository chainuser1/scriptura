import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/data/trails/trail_models.dart';
import 'package:scriptures_reader_mobile/data/user/user_store.dart';

void main() {
  late UserStore s;
  setUp(() => s = UserStore.memory(contract: 'c1'));
  tearDown(() => s.dispose());

  test('a trail keeps its seed, tuning, extra seeds and ordered events', () {
    final t = s.createTrail(name: 'John 3:16', seed: const TrailSeed.verse(26137), moods: ['comfort']);
    s.addTrailSeed(t.id, const TrailSeed.question('How do I forgive?'));
    s.addTrailEvent(t.id, 5, TrailAction.shown);
    s.addTrailEvent(t.id, 5, TrailAction.like);
    s.addTrailEvent(t.id, 9, TrailAction.shown);
    final back = s.trail(t.id)!;
    expect(back.moods, ['comfort']);
    expect(back.seed.verseId, 26137);
    expect(s.trailSeeds(t.id).single.text, 'How do I forgive?');
    expect(s.trailEvents(t.id).map((e) => (e.verseId, e.action)), [(5, TrailAction.shown), (5, TrailAction.like), (9, TrailAction.shown)]);
    s.updateTrail(t.id, name: 'Mercy', focus: 0.9, moods: ['comfort', 'peace'], volume: 'bom');
    final up = s.trail(t.id)!;
    expect((up.name, up.focus, up.volume), ('Mercy', 0.9, 'bom'));
    expect(up.moods, ['comfort', 'peace']);
  });

  test('trails list newest activity first and notify listeners', () async {
    var n = 0;
    s.addListener(() => n++);
    final a = s.createTrail(name: 'A', seed: const TrailSeed.verse(1));
    await Future<void>.delayed(const Duration(milliseconds: 3)); // timestamps are in milliseconds
    final b = s.createTrail(name: 'B', seed: const TrailSeed.verse(2));
    await Future<void>.delayed(const Duration(milliseconds: 3));
    s.addTrailEvent(a.id, 3, TrailAction.shown);
    expect(s.trails().first.id, a.id);
    expect(n, greaterThan(0));
    expect(b.id, isNot(a.id));
  });

  test('delete returns a snapshot that restores the trail exactly', () {
    final t = s.createTrail(name: 'X', seed: const TrailSeed.verse(7));
    s.addTrailEvent(t.id, 8, TrailAction.shown);
    s.addTrailEvent(t.id, 8, TrailAction.dislike);
    final snap = s.deleteTrail(t.id);
    expect(s.trail(t.id), isNull);
    expect(s.trailEvents(t.id), isEmpty);
    s.restoreTrail(snap);
    expect(s.trail(t.id)!.name, 'X');
    expect(s.trailEvents(t.id).length, 2);
  });

  test('likeDislikeEvents spans trails and ignores shown and skip', () {
    final a = s.createTrail(name: 'A', seed: const TrailSeed.verse(1));
    final b = s.createTrail(name: 'B', seed: const TrailSeed.verse(2));
    s.addTrailEvent(a.id, 3, TrailAction.like);
    s.addTrailEvent(b.id, 4, TrailAction.dislike);
    s.addTrailEvent(b.id, 5, TrailAction.skip);
    s.addTrailEvent(b.id, 6, TrailAction.shown);
    // events written in the same millisecond have no defined order across trails, so compare as a set
    expect(s.likeDislikeEvents().map((e) => e.verseId).toSet(), {3, 4});
    expect(s.likeDislikeEvents().length, 2);
  });

  test('a backup carries trails, merges by id, appends only new events and respects the verse range', () {
    final t = s.createTrail(name: 'Keep', seed: const TrailSeed.verse(10));
    s.addTrailEvent(t.id, 11, TrailAction.shown);
    s.addTrailEvent(t.id, 11, TrailAction.like);
    final data = s.exportAll();
    expect((data['trails'] as List).length, 1);

    final fresh = UserStore.memory(contract: 'c1');
    final r1 = fresh.importAll(data, maxVerseId: 100);
    expect(r1.trails, 1);
    expect(fresh.trailEvents(t.id).length, 2);
    final r2 = fresh.importAll(data, maxVerseId: 100); // again: nothing duplicated
    expect(r2.trails, 0);
    expect(fresh.trailEvents(t.id).length, 2);
    // verses outside the layout are dropped, not stored
    final small = UserStore.memory(contract: 'c1');
    small.importAll(data, maxVerseId: 10);
    expect(small.trailEvents(t.id).where((e) => e.verseId > 10), isEmpty);
    fresh.dispose();
    small.dispose();
  });
}
