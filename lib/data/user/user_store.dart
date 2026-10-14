import 'package:flutter/foundation.dart';
import 'package:sqlite3/sqlite3.dart';

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

const _schemaVersion = 1;

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
      };

  /// Merges a backup made by [exportAll]. Nothing is overwritten or removed: bookmarks and highlights that already
  /// exist are kept, notes are added unless the same text is already on that verse. Returns what was added.
  ({int bookmarks, int highlights, int notes}) importAll(Map<String, Object?> data, {int maxVerseId = 1 << 31}) {
    if (data['format'] != 'scriptura-user-data-v1') {
      throw UserDataException('this file is not a Scriptura backup');
    }
    int? vid(Object? v) => v is int && v >= 1 && v <= maxVerseId ? v : null;
    var b = 0, h = 0, n = 0;
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
      _db.execute('COMMIT');
    } on Object {
      _db.execute('ROLLBACK');
      rethrow;
    }
    _changed();
    return (bookmarks: b, highlights: h, notes: n);
  }

  @override
  void dispose() {
    if (_closed) return;
    _closed = true;
    _db.close();
    super.dispose();
  }
}
