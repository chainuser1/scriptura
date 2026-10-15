import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/data/trails/trail_models.dart';
import 'package:scriptures_reader_mobile/services/engine/search_models.dart';

void main() {
  test('a raw request is sent as is, with its request id', () {
    final r = SearchRequest.raw('trail_next', {'k': 10, 'seed': {'verse_id': 7}});
    expect(r.op, 'trail_next');
    expect(r.toJson(42), {'op': 'trail_next', 'k': 10, 'seed': {'verse_id': 7}, 'request_id': 42});
  });

  test('seeds map to the engine wire format', () {
    expect(const TrailSeed.verse(26137).toEngine(), {'verse_id': 26137});
    expect(const TrailSeed.question('How do I forgive?').toEngine(), {'text': 'How do I forgive?'});
    expect(const TrailSeed.entity(TrailSeedKind.place, 'place:zarahemla').toEngine(), {'entity_id': 'place:zarahemla'});
    final back = TrailSeed.fromJson(const TrailSeed.question('x').toJson());
    expect(back.kind, TrailSeedKind.question);
    expect(back.text, 'x');
  });

  test('a trail batch is read from the response', () {
    final res = SearchResponse.fromJson({
      'mode': 'trail',
      'hits': [
        {'verse_id': 5, 'score': 1.5, 'parts': {'genome': 1.0, 'topics': 0.2, 'taste': 0.1, 'novelty': 0.2, 'mood': 0.0, 'explore': true}},
        {'verse_id': 9, 'score': 0.5, 'parts': {'genome': 0.4, 'topics': 0.0, 'taste': 0.0, 'novelty': 0.1, 'mood': 0.0, 'explore': false}},
      ],
      'family_weights': List<double>.filled(23, 0.0)..[18] = 0.9,
      'leans': ['S'],
      'widened': 1,
      'candidates': 80,
    });
    final b = TrailBatch.fromResponse(res);
    expect(b.hits.map((h) => h.verseId), [5, 9]);
    expect(b.hits.first.parts.explore, isTrue);
    expect(b.leans, ['S']);
    expect(b.familyWeights[18], 0.9);
    expect(b.widened, 1);
  });

  test('an explanation and a taste are read from their responses', () {
    final e = ExplainResult.fromResponse(SearchResponse.fromJson({
      'mode': 'explain',
      'families': [
        {'family': 'S', 'share': 0.4, 'genes': [{'id': 'S01_salvific_divine_initiative', 'a': 0.2, 'b': 0.3}]}
      ],
      'mood_matches': ['D18_emotion_comfort_consolation'],
      'shared_terms': ['believeth'],
      'shared_entities': [{'id': 'person:moses', 'name': 'Moses'}],
    }));
    expect(e.families.single.genes.single.id, 'S01_salvific_divine_initiative');
    expect(e.sharedEntities.single.name, 'Moses');
    final t = TasteResult.fromResponse(SearchResponse.fromJson({
      'mode': 'taste',
      'families': [{'family': 'F', 'score': 0.7}]
    }));
    expect(t.single.family, 'F');
  });
}
