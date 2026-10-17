// Request and response models for the search engine. The engine returns verse IDs and scores only; passage text and
// localized references are resolved by the content repository.

class VerseRange {
  const VerseRange(this.first, this.last);
  final int first, last;
  List<int> toJson() => [first, last];
}

class SearchRequest {
  SearchRequest.search(String this.query, {this.language = 'english', this.profile, this.topK = 20, this.filter, this.person})
      : op = 'search',
        phrase = null,
        verseId = null;
  SearchRequest.semantic(String this.query, {this.language = 'english', this.profile, this.topK = 20, this.filter})
      : op = 'semantic',
        phrase = null,
        verseId = null,
        person = null;
  SearchRequest.phrase(String this.phrase, {this.language = 'english', this.topK = 20, this.filter})
      : op = 'phrase',
        query = null,
        profile = null,
        verseId = null,
        person = null;
  SearchRequest.similar(int this.verseId, {this.topK = 10, this.filter})
      : op = 'similar',
        query = null,
        phrase = null,
        language = 'english',
        profile = null,
        person = null;

  SearchRequest.reference(String this.query, {this.language = 'english'})
      : op = 'reference',
        phrase = null,
        verseId = null,
        topK = 1,
        profile = null,
        person = null,
        filter = null;

  /// An engine request whose body is sent as is (the trail operations: `trail_next`, `explain`, `taste`).
  SearchRequest.raw(this.op, Map<String, dynamic> this.body)
      : query = null,
        phrase = null,
        profile = null,
        person = null,
        verseId = null,
        language = 'english',
        topK = 10,
        filter = null;

  final String op;
  final String? query, phrase, profile, person;
  final String language;
  final int topK;
  final int? verseId;
  final List<VerseRange>? filter;

  /// Set only by [SearchRequest.raw].
  Map<String, dynamic>? body;

  Map<String, dynamic> toJson(int requestId) => body != null
      ? {...body!, 'op': op, 'request_id': requestId}
      : {
          'op': op,
          'request_id': requestId,
          if (query != null) 'query': query,
          if (op == 'reference' && query != null) 'text': query, // the engine's reference lookup reads `text`
          if (phrase != null) 'phrase': phrase,
          if (verseId != null) 'verse_id': verseId,
          'language': language,
          'top_k': topK,
          if (profile != null) 'profile': profile,
          if (person != null) 'person': person,
          if (filter != null) 'filter': [for (final r in filter!) r.toJson()],
        };
}

class Hit {
  Hit(this.verseId, this.score);
  final int verseId;
  final double score;
}

class PersonChip {
  PersonChip(this.entityId, this.name, this.qualifier, this.selected);
  final String entityId, name, qualifier;
  final bool selected;
}

class PersonInterpretation {
  PersonInterpretation(this.status, this.people, this.applied);

  /// single | ambiguous | generic
  final String status;
  final List<PersonChip> people;

  /// True when the person's verses were used to order results.
  final bool applied;
}

class ReferenceResult {
  ReferenceResult({
    required this.status,
    this.book,
    this.bookId,
    this.kind,
    this.firstVerseId,
    this.lastVerseId,
    this.reason,
    this.candidates = const [],
  });

  /// ok | ambiguous | out_of_range | not_a_reference
  final String status;
  final String? book, kind, reason;
  final int? bookId, firstVerseId, lastVerseId;
  final List<({int bookId, String book})> candidates;

  factory ReferenceResult.fromJson(Map<String, dynamic> j) => ReferenceResult(
        status: j['status'] as String,
        book: j['book'] as String?,
        bookId: j['book_id'] as int?,
        kind: j['kind'] as String?,
        firstVerseId: j['first_verse_id'] as int?,
        lastVerseId: j['last_verse_id'] as int?,
        reason: j['reason'] as String?,
        candidates: [
          for (final c in (j['candidates'] as List? ?? const [])) (bookId: c['book_id'] as int, book: c['book'] as String)
        ],
      );
}

class SearchResponse {
  SearchResponse({
    required this.mode,
    this.requestId,
    this.hits = const [],
    this.total,
    this.truncated = false,
    this.reference,
    this.person,
    this.profile,
    this.requestedProfile,
    this.configurationId,
    this.totalMs,
    this.encodeMs,
    this.searchMs,
    this.raw = const {},
  });

  /// semantic | phrase | similar | reference
  final String mode;
  final int? requestId, total;
  final List<Hit> hits;
  final bool truncated;
  final ReferenceResult? reference;
  final PersonInterpretation? person;
  final String? profile, requestedProfile, configurationId;
  final double? totalMs, encodeMs, searchMs;

  /// The decoded response body, for operations whose payload has no typed field (trail_next, explain, taste).
  final Map<String, dynamic> raw;

  /// The profile fell back (for example Thread-based profiles when the ColBERT pack is not installed).
  bool get profileFellBack => profile != null && requestedProfile != null && profile != requestedProfile;

  factory SearchResponse.fromJson(Map<String, dynamic> j) {
    final mode = j['mode'] as String;
    final hits = <Hit>[
      for (final h in (j['hits'] as List? ?? const [])) Hit(h['verse_id'] as int, (h['score'] as num).toDouble()),
      for (final v in (j['verse_ids'] as List? ?? const [])) Hit(v as int, 0),
    ];
    PersonInterpretation? person;
    final p = (j['interpretation'] as Map?)?['person'] as Map?;
    if (p != null) {
      person = PersonInterpretation(
        p['status'] as String,
        [
          for (final c in p['people'] as List)
            PersonChip(c['entity_id'] as String, c['name'] as String, c['qualifier'] as String, c['selected'] as bool)
        ],
        p['applied'] as bool,
      );
    }
    return SearchResponse(
      mode: mode,
      requestId: j['request_id'] as int?,
      hits: hits,
      total: j['total'] as int?,
      truncated: j['truncated'] as bool? ?? false,
      reference: j['reference'] == null ? null : ReferenceResult.fromJson((j['reference'] as Map).cast<String, dynamic>()),
      person: person,
      profile: j['profile'] as String?,
      requestedProfile: j['requested_profile'] as String?,
      configurationId: j['configuration_id'] as String?,
      totalMs: ((j['timings_ms'] as Map?)?['total'] as num?)?.toDouble(),
      encodeMs: ((j['timings_ms'] as Map?)?['encode'] as num?)?.toDouble(),
      searchMs: ((j['timings_ms'] as Map?)?['search'] as num?)?.toDouble(),
      raw: j,
    );
  }
}

/// Typed failure with the engine's error code (invalid_input, unsupported_language, cancelled, missing_pack, ...).
class SearchFailure implements Exception {
  SearchFailure(this.code, this.message);
  final String code, message;
  bool get cancelled => code == 'cancelled';
  @override
  String toString() => 'SearchFailure($code): $message';
}
