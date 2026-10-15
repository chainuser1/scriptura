import '../../services/engine/search_models.dart';

enum TrailAction { shown, like, skip, dislike }

TrailAction? trailActionOf(String s) {
  for (final a in TrailAction.values) {
    if (a.name == s) return a;
  }
  return null;
}

enum TrailSeedKind { verse, question, person, place }

class TrailSeed {
  const TrailSeed.verse(int this.verseId)
      : kind = TrailSeedKind.verse,
        text = null,
        entityId = null;
  const TrailSeed.question(String this.text)
      : kind = TrailSeedKind.question,
        verseId = null,
        entityId = null;
  const TrailSeed.entity(this.kind, String this.entityId, {this.text}) : verseId = null;

  final TrailSeedKind kind;
  final int? verseId;
  final String? text, entityId;

  Map<String, dynamic> toEngine() => switch (kind) {
        TrailSeedKind.verse => {'verse_id': verseId},
        TrailSeedKind.question => {'text': text},
        _ => {'entity_id': entityId},
      };

  Map<String, dynamic> toJson() => {'kind': kind.name, 'verse_id': verseId, 'text': text, 'entity_id': entityId};

  factory TrailSeed.fromJson(Map<String, dynamic> j) {
    final kind = TrailSeedKind.values.firstWhere((k) => k.name == j['kind'], orElse: () => TrailSeedKind.verse);
    return switch (kind) {
      TrailSeedKind.verse => TrailSeed.verse(j['verse_id'] as int),
      TrailSeedKind.question => TrailSeed.question(j['text'] as String),
      _ => TrailSeed.entity(kind, j['entity_id'] as String, text: j['text'] as String?),
    };
  }
}

class Trail {
  Trail({
    required this.id,
    required this.name,
    required this.seed,
    this.focus = 0.5,
    this.moods = const [],
    this.moodStrength = 0.5,
    this.volume = 'all',
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String name;
  final TrailSeed seed;
  final double focus, moodStrength;
  final List<String> moods; // mood ids from assets/trail_moods.json, at most two
  final String volume; // all | ot | nt | bible | bom | dc | pgp
  final DateTime createdAt, updatedAt;

  Trail copyWith({String? name, double? focus, List<String>? moods, double? moodStrength, String? volume, DateTime? updatedAt}) => Trail(
        id: id,
        name: name ?? this.name,
        seed: seed,
        focus: focus ?? this.focus,
        moods: moods ?? this.moods,
        moodStrength: moodStrength ?? this.moodStrength,
        volume: volume ?? this.volume,
        createdAt: createdAt,
        updatedAt: updatedAt ?? this.updatedAt,
      );
}

class TrailEvent {
  const TrailEvent(this.verseId, this.action, this.at);
  final int verseId;
  final TrailAction action;
  final DateTime at;
}

class TrailSnapshot {
  const TrailSnapshot(this.trail, this.seeds, this.events);
  final Trail trail;
  final List<TrailSeed> seeds;
  final List<TrailEvent> events;
}

class TrailHitParts {
  const TrailHitParts({this.genome = 0, this.topics = 0, this.taste = 0, this.novelty = 0, this.mood = 0, this.explore = false});
  final double genome, topics, taste, novelty, mood;
  final bool explore;
}

class TrailHit {
  const TrailHit(this.verseId, this.score, this.parts);
  final int verseId;
  final double score;
  final TrailHitParts parts;
}

double _d(Object? v) => (v as num?)?.toDouble() ?? 0.0;

class TrailBatch {
  TrailBatch(this.hits, this.familyWeights, this.leans, this.widened, this.candidates);
  final List<TrailHit> hits;
  final List<double> familyWeights;
  final List<String> leans;
  final int widened, candidates;

  factory TrailBatch.fromResponse(SearchResponse r) {
    final j = r.raw;
    return TrailBatch(
      [
        for (final h in (j['hits'] as List? ?? const []).cast<Map>())
          TrailHit(
            h['verse_id'] as int,
            _d(h['score']),
            () {
              final p = (h['parts'] as Map?) ?? const {};
              return TrailHitParts(
                  genome: _d(p['genome']), topics: _d(p['topics']), taste: _d(p['taste']), novelty: _d(p['novelty']), mood: _d(p['mood']), explore: p['explore'] == true);
            }(),
          )
      ],
      [for (final x in (j['family_weights'] as List? ?? const [])) _d(x)],
      [for (final x in (j['leans'] as List? ?? const [])) '$x'],
      (j['widened'] as int?) ?? 0,
      (j['candidates'] as int?) ?? 0,
    );
  }
}

class GeneShare {
  const GeneShare(this.id, this.a, this.b);
  final String id;
  final double a, b;
}

class FamilyShare {
  const FamilyShare(this.family, this.share, this.genes);
  final String family;
  final double share;
  final List<GeneShare> genes;
}

class SharedEntity {
  const SharedEntity(this.id, this.name);
  final String id, name;
}

class ExplainResult {
  ExplainResult(this.families, this.moodMatches, this.sharedTerms, this.sharedEntities);
  final List<FamilyShare> families;
  final List<String> moodMatches, sharedTerms;
  final List<SharedEntity> sharedEntities;

  factory ExplainResult.fromResponse(SearchResponse r) {
    final j = r.raw;
    return ExplainResult(
      [
        for (final f in (j['families'] as List? ?? const []).cast<Map>())
          FamilyShare(f['family'] as String, _d(f['share']), [
            for (final g in (f['genes'] as List? ?? const []).cast<Map>()) GeneShare(g['id'] as String, _d(g['a']), _d(g['b'])),
          ])
      ],
      [for (final x in (j['mood_matches'] as List? ?? const [])) '$x'],
      [for (final x in (j['shared_terms'] as List? ?? const [])) '$x'],
      [for (final e in (j['shared_entities'] as List? ?? const []).cast<Map>()) SharedEntity(e['id'] as String, (e['name'] as String?) ?? '')],
    );
  }
}

class FamilyScore {
  const FamilyScore(this.family, this.score);
  final String family;
  final double score;
}

abstract final class TasteResult {
  static List<FamilyScore> fromResponse(SearchResponse r) =>
      [for (final f in (r.raw['families'] as List? ?? const []).cast<Map>()) FamilyScore(f['family'] as String, _d(f['score']))];
}
