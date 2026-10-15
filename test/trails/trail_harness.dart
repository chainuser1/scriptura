import 'package:scriptures_reader_mobile/data/content/catalog.dart';
import 'package:scriptures_reader_mobile/data/content/content_database.dart';
import 'package:scriptures_reader_mobile/data/content/content_repository.dart';
import 'package:scriptures_reader_mobile/features/trails/trail_catalog.dart';
import 'package:scriptures_reader_mobile/services/engine/search_models.dart';

ContentRepository fixtureRepository() {
  final db = ContentDatabase.open('test/fixtures/content_v2_mini.db');
  return ContentRepository(db, Catalog.load('test/fixtures/catalog_mini.db', contract: db.contract));
}

TrailCatalog testCatalog() => TrailCatalog.fromJson(
      {
        'moods': [
          {'id': 'comfort', 'label': 'Comfort', 'blurb': 'Consoling verses', 'genes': [{'id': 'D18_emotion_comfort_consolation', 'weight': 1.0}]},
          {'id': 'peace', 'label': 'Peace', 'blurb': 'Still verses', 'genes': [{'id': 'D08_emotion_peace_stillness', 'weight': 1.0}]},
        ]
      },
      {
        'starters': [
          {'id': 'comfort', 'title': 'Finding comfort', 'blurb': 'When grief is heavy', 'mood': 'comfort', 'question': 'Where can I find comfort?', 'icon': 'favorite_border'}
        ]
      },
      {
        'families': {'S': 'Salvation', 'F': 'Divine reference', 'D': 'Emotion'},
        'genes': {'S01_salvific_divine_initiative': 'Divine initiative', 'D18_emotion_comfort_consolation': 'Comfort and consolation'}
      },
    );

/// A trail batch response for the fake engine.
SearchResponse batchOf(List<int> verses, {List<String> leans = const [], int widened = 0}) => SearchResponse.fromJson({
      'mode': 'trail',
      'hits': [
        for (var i = 0; i < verses.length; i++)
          {'verse_id': verses[i], 'score': 1.0 - i * 0.1, 'parts': {'genome': 1.0, 'topics': 0.0, 'taste': 0.0, 'novelty': 0.1, 'mood': 0.0, 'explore': false}}
      ],
      'family_weights': List<double>.filled(23, 0.0),
      'leans': leans,
      'widened': widened,
      'candidates': verses.length,
    });
