import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:sqlite3/sqlite3.dart';

import '../trails/trail_models.dart';

/// Personal data lives only on this device, in `user.db`. Verse IDs follow the content release's verse-order contract;
/// a database written for a different contract is refused, never altered.
class UserDataException implements Exception {
  UserDataException(this.message);
  final String message;
  @override
  String toString() => 'UserDataException: $message';
}

class Bookmark {
  Bookmark(this.verseId, this.createdAt);
  final int verseId;
  final DateTime createdAt;
}

class Highlight {
  Highlight(this.verseId, this.color);
  final int verseId;

  /// Index into the app's highlight palette (0 = yellow).
  final int color;
}

class Note {
  Note(this.id, this.verseId, this.text, this.createdAt, this.updatedAt);
  final int id, verseId;
  final String text;
  final DateTime createdAt, updatedAt;
}

class ReadingPosition {
  const ReadingPosition(this.bookId, this.chapter, [this.verse]);
  final int bookId, chapter;
  final int? verse;
}

const _schemaVersion = 2;

class UserStore extends ChangeNotifier {
  UserStore._(this._db);

  final Database _db;
  var _closed = false;

  static UserStore open(String path, {required String contract}) {
    final db = sqlite3.open(path);
    return UserStore._(db).._init(contract);
  }

  /// In-memory store for tests and fixed-controller widget tests.
  static UserStore memory({String contract = ''}) => UserStore._(sqlite3.openInMemory()).._init(contract);

  void _init(String contract) {
    _db.execute('PRAGMA journal_mode = WAL');
    _db.execute('PRAGMA foreign_keys = ON');
    final version = _db.select('PRAGMA user_version').first.values.first as int;
    if (version > _schemaVersion) {
      throw UserDataException('user data was written by a newer version of the app');
    }
    if (version < 1) {
      _db.execute('''
        CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
        CREATE TABLE bookmarks(verse_id INTEGER PRIMARY KEY, created_at INTEGER NOT NULL) WITHOUT ROWID;
        CREATE TABLE highlights(verse_id INTEGER PRIMARY KEY, color INTEGER NOT NULL, created_at INTEGER NOT NULL) WITHOUT ROWID;
        CREATE TABLE notes(id INTEGER PRIMARY KEY AUTOINCREMENT, verse_id INTEGER NOT NULL, body TEXT NOT NULL,
                           created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
        CREATE INDEX notes_verse ON notes(verse_id);
        CREATE TABLE searches(id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT NOT NULL, mode TEXT NOT NULL, at INTEGER NOT NULL);
        CREATE TABLE prefs(key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
        PRAGMA user_version = 1;
      ''');
    }
    if (version < 2) {
      _db.execute('''
        CREATE TABLE trails(id TEXT PRIMARY KEY, name TEXT NOT NULL,
                            seed_kind TEXT NOT NULL CHECK(seed_kind IN ('verse','question','person','place')),
                            seed_verse INTEGER, seed_text TEXT, seed_entity TEXT, focus REAL NOT NULL DEFAULT 0.5, moods TEXT NOT NULL DEFAULT '[]',
                            mood_strength REAL NOT NULL DEFAULT 0.5, volume TEXT NOT NULL DEFAULT 'all',
                            created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL) WITHOUT ROWID;
        CREATE TABLE trail_seeds(trail_id TEXT NOT NULL, seq INTEGER NOT NULL,
                                 kind TEXT NOT NULL CHECK(kind IN ('verse','question','person','place')),
                                 verse_id INTEGER, text TEXT, entity_id TEXT, PRIMARY KEY(trail_id, seq)) WITHOUT ROWID;
        CREATE TABLE trail_events(trail_id TEXT NOT NULL, seq INTEGER NOT NULL, verse_id INTEGER NOT NULL,
                                  action TEXT NOT NULL CHECK(action IN ('shown','like','skip','dislike')), at INTEGER NOT NULL,
                                  PRIMARY KEY(trail_id, seq)) WITHOUT ROWID;
        PRAGMA user_version = 2;
      ''');
    }
    final stored = _db.select("SELECT value FROM meta WHERE key = 'verse_order_sha256'");
    if (stored.isEmpty) {
      _db.execute("INSERT INTO meta VALUES ('verse_order_sha256', ?)", [contract]);
    } else if (contract.isNotEmpty && stored.first['value'] != contract && stored.first['value'] != '') {
      _db.close();
      throw UserDataException('your saved data belongs to a different verse layout; it was left untouched');
    } else if (stored.first['value'] == '' && contract.isNotEmpty) {
      _db.execute("UPDATE meta SET value = ? WHERE key = 'verse_order_sha256'", [contract]);
    }
  }

  static int _now() => DateTime.now().millisecondsSinceEpoch;
  static DateTime _t(Object? ms) => DateTime.fromMillisecondsSinceEpoch(ms as int);

  void _changed() {
    if (!_closed) notifyListeners();
  }

  // ---- bookmarks ----------------------------------------------------------------------------------------------------
  List<Bookmark> bookmarks() => [
        for (final r in _db.select('SELECT verse_id, created_at FROM bookmarks ORDER BY created_at DESC'))
          Bookmark(r['verse_id'] as int, _t(r['created_at']))
      ];

  bool isBookmarked(int verseId) => _db.select('SELECT 1 FROM bookmarks WHERE verse_id = ?', [verseId]).isNotEmpty;

  /// Returns the new state.
  bool toggleBookmark(int verseId) {
    final on = !isBookmarked(verseId);
    if (on) {
      _db.execute('INSERT INTO bookmarks VALUES (?, ?)', [verseId, _now()]);
    } else {
      _db.execute('DELETE FROM bookmarks WHERE verse_id = ?', [verseId]);
    }
    _changed();
    return on;
  }

  // ---- highlights ---------------------------------------------------------------------------------------------------
  Map<int, int> highlightsIn(int firstVerseId, int lastVerseId) => {
        for (final r in _db.select('SELECT verse_id, color FROM highlights WHERE verse_id BETWEEN ? AND ?', [firstVerseId, lastVerseId]))
          r['verse_id'] as int: r['color'] as int
      };

  List<Highlight> highlights() => [
        for (final r in _db.select('SELECT verse_id, color FROM highlights ORDER BY created_at DESC'))
          Highlight(r['verse_id'] as int, r['color'] as int)
      ];

  /// Same colour again removes the highlight.
  void toggleHighlight(int verseId, int color) {
    final cur = _db.select('SELECT color FROM highlights WHERE verse_id = ?', [verseId]);
    if (cur.isNotEmpty && cur.first['color'] == color) {
      _db.execute('DELETE FROM highlights WHERE verse_id = ?', [verseId]);
    } else {
      _db.execute('INSERT OR REPLACE INTO highlights VALUES (?, ?, ?)', [verseId, color, _now()]);
    }
    _changed();
  }

  // ---- notes --------------------------------------------------------------------------------------------------------
  List<Note> notes({int? verseId}) => [
        for (final r in verseId == null
            ? _db.select('SELECT * FROM notes ORDER BY updated_at DESC')
            : _db.select('SELECT * FROM notes WHERE verse_id = ? ORDER BY created_at', [verseId]))
          Note(r['id'] as int, r['verse_id'] as int, r['body'] as String, _t(r['created_at']), _t(r['updated_at']))
      ];

  int noteCountFor(int verseId) => _db.select('SELECT COUNT(*) c FROM notes WHERE verse_id = ?', [verseId]).first['c'] as int;

  Set<int> versesWithNotes(int firstVerseId, int lastVerseId) => {
        for (final r in _db.select('SELECT DISTINCT verse_id FROM notes WHERE verse_id BETWEEN ? AND ?', [firstVerseId, lastVerseId]))
          r['verse_id'] as int
      };

  Set<int> bookmarkedIn(int firstVerseId, int lastVerseId) => {
        for (final r in _db.select('SELECT verse_id FROM bookmarks WHERE verse_id BETWEEN ? AND ?', [firstVerseId, lastVerseId]))
          r['verse_id'] as int
      };

  int addNote(int verseId, String body) {
    final text = body.trim();
    if (text.isEmpty) throw UserDataException('a note cannot be empty');
    final now = _now();
    _db.execute('INSERT INTO notes(verse_id, body, created_at, updated_at) VALUES (?, ?, ?, ?)', [verseId, text, now, now]);
    final id = _db.lastInsertRowId;
    _changed();
    return id;
  }

  void updateNote(int id, String body) {
    final text = body.trim();
    if (text.isEmpty) throw UserDataException('a note cannot be empty');
    _db.execute('UPDATE notes SET body = ?, updated_at = ? WHERE id = ?', [text, _now(), id]);
    _changed();
  }

  void deleteNote(int id) {
    _db.execute('DELETE FROM notes WHERE id = ?', [id]);
    _changed();
  }

  // ---- search history -----------------------------------------------------------------------------------------------
  List<({String query, String mode})> recentSearches({int limit = 8}) => [
        for (final r in _db.select('SELECT query, mode FROM searches ORDER BY id DESC LIMIT ?', [limit * 3]))
          (query: r['query'] as String, mode: r['mode'] as String)
      ].fold<List<({String query, String mode})>>([], (a, e) {
        if (a.length < limit && !a.any((x) => x.query == e.query && x.mode == e.mode)) a.add(e);
        return a;
      });

  void rememberSearch(String query, String mode) {
    final q = query.trim();
    if (q.isEmpty) return;
    _db.execute('INSERT INTO searches(query, mode, at) VALUES (?, ?, ?)', [q, mode, _now()]);
    _db.execute('DELETE FROM searches WHERE id NOT IN (SELECT id FROM searches ORDER BY id DESC LIMIT 200)');
    _changed();
  }

  void clearSearchHistory() {
    _db.execute('DELETE FROM searches');
    _changed();
  }

  // ---- preferences and reading position -----------------------------------------------------------------------------
  String? pref(String key) {
    final r = _db.select('SELECT value FROM prefs WHERE key = ?', [key]);
    return r.isEmpty ? null : r.first['value'] as String;
  }

  void setPref(String key, String value) {
    _db.execute('INSERT OR REPLACE INTO prefs VALUES (?, ?)', [key, value]);
    _changed();
  }

  double prefDouble(String key, double fallback) => double.tryParse(pref(key) ?? '') ?? fallback;
  int prefInt(String key, int fallback) => int.tryParse(pref(key) ?? '') ?? fallback;

  ReadingPosition? get position {
    final p = pref('position');
    if (p == null) return null;
    final parts = p.split(':').map(int.tryParse).toList();
    if (parts.length < 2 || parts[0] == null || parts[1] == null) return null;
    return ReadingPosition(parts[0]!, parts[1]!, parts.length > 2 ? parts[2] : null);
  }

  void savePosition(int bookId, int chapter, [int? verse]) {
    // not notifying: the position is written on every chapter change and nothing listens for it
    _db.execute('INSERT OR REPLACE INTO prefs VALUES (?, ?)', ['position', '$bookId:$chapter${verse == null ? '' : ':$verse'}']);
  }

  // ---- trails -------------------------------------------------------------------------------------------------------
  static final _rng = Random.secure();

  String _newId() => List.generate(16, (_) => _rng.nextInt(256).toRadixString(16).padLeft(2, '0')).join();

  Trail _trailFrom(Row r) {
    final kind = r['seed_kind'] as String;
    final seed = switch (kind) {
      'verse' => TrailSeed.verse(r['seed_verse'] as int),
      'person' => TrailSeed.entity(TrailSeedKind.person, r['seed_entity'] as String, text: r['seed_text'] as String?),
      'place' => TrailSeed.entity(TrailSeedKind.place, r['seed_entity'] as String, text: r['seed_text'] as String?),
      _ => TrailSeed.question((r['seed_text'] as String?) ?? ''),
    };
    return Trail(
      id: r['id'] as String,
      name: r['name'] as String,
      seed: seed,
      focus: (r['focus'] as num).toDouble(),
      moods: List<String>.from(jsonDecode(r['moods'] as String) as List),
      moodStrength: (r['mood_strength'] as num).toDouble(),
      volume: r['volume'] as String,
      createdAt: DateTime.fromMillisecondsSinceEpoch(r['created_at'] as int),
      updatedAt: DateTime.fromMillisecondsSinceEpoch(r['updated_at'] as int),
    );
  }

  Trail createTrail({
    required String name,
    required TrailSeed seed,
    List<String> moods = const [],
    String volume = 'all',
    double focus = 0.5,
    double moodStrength = 0.5,
  }) {
    final id = _newId();
    final now = _now();
    _db.execute(
      'INSERT INTO trails(id, name, seed_kind, seed_verse, seed_text, seed_entity, focus, moods, mood_strength, volume, created_at, updated_at) '
      'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
      [id, name, seed.kind.name, seed.verseId, seed.text, seed.entityId, focus, jsonEncode(moods), moodStrength, volume, now, now],
    );
    _changed();
    return _trailFrom(_db.select('SELECT * FROM trails WHERE id = ?', [id]).first);
  }

  List<Trail> trails() => [for (final r in _db.select('SELECT * FROM trails ORDER BY updated_at DESC, created_at DESC')) _trailFrom(r)];

  Trail? trail(String id) {
    final rows = _db.select('SELECT * FROM trails WHERE id = ?', [id]);
    return rows.isEmpty ? null : _trailFrom(rows.first);
  }

  void updateTrail(String id, {String? name, double? focus, List<String>? moods, double? moodStrength, String? volume}) {
    final t = trail(id);
    if (t == null) return;
    _db.execute(
      'UPDATE trails SET name = ?, focus = ?, moods = ?, mood_strength = ?, volume = ?, updated_at = ? WHERE id = ?',
      [name ?? t.name, focus ?? t.focus, jsonEncode(moods ?? t.moods), moodStrength ?? t.moodStrength, volume ?? t.volume, _now(), id],
    );
    _changed();
  }

  void addTrailSeed(String id, TrailSeed seed) {
    final seq = (_db.select('SELECT COALESCE(MAX(seq), -1) + 1 AS n FROM trail_seeds WHERE trail_id = ?', [id]).first['n'] as int);
    _db.execute('INSERT INTO trail_seeds VALUES (?, ?, ?, ?, ?, ?)', [id, seq, seed.kind.name, seed.verseId, seed.text, seed.entityId]);
    _db.execute('UPDATE trails SET updated_at = ? WHERE id = ?', [_now(), id]);
    _changed();
  }

  List<TrailSeed> trailSeeds(String id) => [
        for (final r in _db.select('SELECT * FROM trail_seeds WHERE trail_id = ? ORDER BY seq', [id]))
          TrailSeed.fromJson({'kind': r['kind'], 'verse_id': r['verse_id'], 'text': r['text'], 'entity_id': r['entity_id']})
      ];

  void addTrailEvent(String id, int verseId, TrailAction action) {
    final seq = (_db.select('SELECT COALESCE(MAX(seq), -1) + 1 AS n FROM trail_events WHERE trail_id = ?', [id]).first['n'] as int);
    final now = _now();
    _db.execute('INSERT INTO trail_events VALUES (?, ?, ?, ?, ?)', [id, seq, verseId, action.name, now]);
    _db.execute('UPDATE trails SET updated_at = ? WHERE id = ?', [now, id]);
    _changed();
  }

  List<TrailEvent> trailEvents(String id) => [
        for (final r in _db.select('SELECT verse_id, action, at FROM trail_events WHERE trail_id = ? ORDER BY seq', [id]))
          TrailEvent(r['verse_id'] as int, trailActionOf(r['action'] as String)!, DateTime.fromMillisecondsSinceEpoch(r['at'] as int))
      ];

  List<TrailEvent> likeDislikeEvents() => [
        for (final r in _db.select("SELECT verse_id, action, at FROM trail_events WHERE action IN ('like', 'dislike') ORDER BY at, trail_id, seq"))
          TrailEvent(r['verse_id'] as int, trailActionOf(r['action'] as String)!, DateTime.fromMillisecondsSinceEpoch(r['at'] as int))
      ];

  /// Removes every like and dislike from every trail (taste reset). Returns what was removed, for Undo.
  List<({String trailId, int seq, int verseId, String action, int at})> clearFeedback() {
    final rows = [
      for (final r in _db.select("SELECT trail_id, seq, verse_id, action, at FROM trail_events WHERE action IN ('like', 'dislike')"))
        (trailId: r['trail_id'] as String, seq: r['seq'] as int, verseId: r['verse_id'] as int, action: r['action'] as String, at: r['at'] as int)
    ];
    _db.execute("DELETE FROM trail_events WHERE action IN ('like', 'dislike')");
    _changed();
    return rows;
  }

  void restoreFeedback(List<({String trailId, int seq, int verseId, String action, int at})> rows) {
    for (final r in rows) {
      _db.execute('INSERT OR IGNORE INTO trail_events VALUES (?, ?, ?, ?, ?)', [r.trailId, r.seq, r.verseId, r.action, r.at]);
    }
    _changed();
  }

  TrailSnapshot deleteTrail(String id) {
    final snap = TrailSnapshot(trail(id)!, trailSeeds(id), trailEvents(id));
    _db.execute('DELETE FROM trail_events WHERE trail_id = ?', [id]);
    _db.execute('DELETE FROM trail_seeds WHERE trail_id = ?', [id]);
    _db.execute('DELETE FROM trails WHERE id = ?', [id]);
    _changed();
    return snap;
  }

  void restoreTrail(TrailSnapshot s) {
    final t = s.trail;
    _db.execute(
      'INSERT OR REPLACE INTO trails(id, name, seed_kind, seed_verse, seed_text, seed_entity, focus, moods, mood_strength, volume, created_at, updated_at) '
      'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
      [t.id, t.name, t.seed.kind.name, t.seed.verseId, t.seed.text, t.seed.entityId, t.focus, jsonEncode(t.moods), t.moodStrength, t.volume,
        t.createdAt.millisecondsSinceEpoch, t.updatedAt.millisecondsSinceEpoch],
    );
    var seq = 0;
    for (final x in s.seeds) {
      _db.execute('INSERT OR REPLACE INTO trail_seeds VALUES (?, ?, ?, ?, ?, ?)', [t.id, seq++, x.kind.name, x.verseId, x.text, x.entityId]);
    }
    seq = 0;
    for (final e in s.events) {
      _db.execute('INSERT OR REPLACE INTO trail_events VALUES (?, ?, ?, ?, ?)', [t.id, seq++, e.verseId, e.action.name, e.at.millisecondsSinceEpoch]);
    }
    _changed();
  }

  // ---- backup -------------------------------------------------------------------------------------------------------
  /// Everything a person created, as plain data (for export and backup).
  Map<String, Object?> exportAll() => {
        'format': 'scriptura-user-data-v1',
        'bookmarks': [for (final b in bookmarks()) {'verse_id': b.verseId, 'created_at': b.createdAt.toIso8601String()}],
        'highlights': [for (final h in highlights()) {'verse_id': h.verseId, 'color': h.color}],
        'notes': [
          for (final n in notes())
            {'verse_id': n.verseId, 'text': n.text, 'created_at': n.createdAt.toIso8601String(), 'updated_at': n.updatedAt.toIso8601String()}
        ],
        'trails': [
          for (final t in trails())
            {
              'id': t.id,
              'name': t.name,
              'seed_kind': t.seed.kind.name,
              'seed_verse': t.seed.verseId,
              'seed_text': t.seed.text,
              'seed_entity': t.seed.entityId,
              'focus': t.focus,
              'moods': t.moods,
              'mood_strength': t.moodStrength,
              'volume': t.volume,
              'created_at': t.createdAt.toIso8601String(),
              'updated_at': t.updatedAt.toIso8601String(),
              'seeds': [for (final x in trailSeeds(t.id)) x.toJson()],
              'events': [for (final e in trailEvents(t.id)) {'verse_id': e.verseId, 'action': e.action.name, 'at': e.at.toIso8601String()}],
            }
        ],
      };

  /// Merges a backup made by [exportAll]. Nothing is overwritten or removed: bookmarks and highlights that already
  /// exist are kept, notes are added unless the same text is already on that verse. Returns what was added.
  ({int bookmarks, int highlights, int notes, int trails}) importAll(Map<String, Object?> data, {int maxVerseId = 1 << 31}) {
    if (data['format'] != 'scriptura-user-data-v1') {
      throw UserDataException('this file is not a Scriptura backup');
    }
    int? vid(Object? v) => v is int && v >= 1 && v <= maxVerseId ? v : null;
    var b = 0, h = 0, n = 0, tr = 0;
    _db.execute('BEGIN');
    try {
      for (final e in (data['bookmarks'] as List? ?? const [])) {
        final v = vid((e as Map)['verse_id']);
        if (v == null || isBookmarked(v)) continue;
        final at = DateTime.tryParse('${e['created_at']}')?.millisecondsSinceEpoch ?? _now();
        _db.execute('INSERT INTO bookmarks VALUES (?, ?)', [v, at]);
        b++;
      }
      for (final e in (data['highlights'] as List? ?? const [])) {
        final v = vid((e as Map)['verse_id']);
        final c = e['color'];
        if (v == null || c is! int || _db.select('SELECT 1 FROM highlights WHERE verse_id = ?', [v]).isNotEmpty) continue;
        _db.execute('INSERT INTO highlights VALUES (?, ?, ?)', [v, c, _now()]);
        h++;
      }
      for (final e in (data['notes'] as List? ?? const [])) {
        final v = vid((e as Map)['verse_id']);
        final text = '${e['text'] ?? ''}'.trim();
        if (v == null || text.isEmpty) continue;
        if (_db.select('SELECT 1 FROM notes WHERE verse_id = ? AND body = ?', [v, text]).isNotEmpty) continue;
        final created = DateTime.tryParse('${e['created_at']}')?.millisecondsSinceEpoch ?? _now();
        final updated = DateTime.tryParse('${e['updated_at']}')?.millisecondsSinceEpoch ?? created;
        _db.execute('INSERT INTO notes(verse_id, body, created_at, updated_at) VALUES (?, ?, ?, ?)', [v, text, created, updated]);
        n++;
      }
      for (final raw in (data['trails'] as List? ?? const [])) {
        final j = (raw as Map).cast<String, dynamic>();
        final id = j['id'];
        if (id is! String || id.isEmpty) continue;
        final kind = j['seed_kind'];
        if (kind is! String || !const {'verse', 'question', 'person', 'place'}.contains(kind)) continue;
        if (kind == 'verse' && vid(j['seed_verse']) == null) continue;
        if (_db.select('SELECT 1 FROM trails WHERE id = ?', [id]).isEmpty) {
          _db.execute(
            'INSERT INTO trails(id, name, seed_kind, seed_verse, seed_text, seed_entity, focus, moods, mood_strength, volume, created_at, updated_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            [
              id,
              '${j['name'] ?? 'Trail'}',
              kind,
              j['seed_verse'],
              j['seed_text'],
              j['seed_entity'],
              (j['focus'] as num?)?.toDouble() ?? 0.5,
              jsonEncode(j['moods'] ?? const []),
              (j['mood_strength'] as num?)?.toDouble() ?? 0.5,
              '${j['volume'] ?? 'all'}',
              DateTime.tryParse('${j['created_at']}')?.millisecondsSinceEpoch ?? _now(),
              DateTime.tryParse('${j['updated_at']}')?.millisecondsSinceEpoch ?? _now(),
            ],
          );
          var seq = 0;
          for (final x in (j['seeds'] as List? ?? const [])) {
            final m = (x as Map).cast<String, dynamic>();
            if (m['kind'] == 'verse' && vid(m['verse_id']) == null) continue;
            _db.execute('INSERT INTO trail_seeds VALUES (?, ?, ?, ?, ?, ?)', [id, seq++, m['kind'], m['verse_id'], m['text'], m['entity_id']]);
          }
          tr++;
        }
        var next = _db.select('SELECT COALESCE(MAX(seq), -1) + 1 AS n FROM trail_events WHERE trail_id = ?', [id]).first['n'] as int;
        for (final e in (j['events'] as List? ?? const [])) {
          final m = (e as Map).cast<String, dynamic>();
          final v = vid(m['verse_id']);
          final a = trailActionOf('${m['action']}');
          final at = DateTime.tryParse('${m['at']}')?.millisecondsSinceEpoch;
          if (v == null || a == null || at == null) continue;
          final dup = _db.select(
              'SELECT 1 FROM trail_events WHERE trail_id = ? AND verse_id = ? AND action = ? AND at = ?', [id, v, a.name, at]);
          if (dup.isNotEmpty) continue;
          _db.execute('INSERT INTO trail_events VALUES (?, ?, ?, ?, ?)', [id, next++, v, a.name, at]);
        }
      }
      _db.execute('COMMIT');
    } on Object {
      _db.execute('ROLLBACK');
      rethrow;
    }
    _changed();
    return (bookmarks: b, highlights: h, notes: n, trails: tr);
  }

  @override
  void dispose() {
    if (_closed) return;
    _closed = true;
    _db.close();
    super.dispose();
  }
}
