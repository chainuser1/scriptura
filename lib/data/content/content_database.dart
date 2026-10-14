import 'dart:io';

import 'package:sqlite3/sqlite3.dart';

enum ContentErrorKind { missing, notSqlite, wrongKind, wrongDimensions, notFound, unsupportedLanguage }

class ContentException implements Exception {
  ContentException(this.kind, this.message);
  final ContentErrorKind kind;
  final String message;
  @override
  String toString() => 'ContentException(${kind.name}): $message';
}

class ProvenanceRange {
  const ProvenanceRange(this.firstVerseId, this.lastVerseId, this.source, this.qualityTier);
  final int firstVerseId, lastVerseId;
  final String source, qualityTier;
}

/// SQL-safety allowlist: which text table a language name may map to. NOT the serving list.
const supportedLanguages = <String, String>{
  'english': 'text_english',
  'spanish': 'text_spanish',
  'tagalog': 'text_tagalog',
  'cebuano': 'text_cebuano',
  'greek': 'text_greek',
  'french': 'text_french',
  'german': 'text_german',
  'hebrew': 'text_hebrew',
};

/// A validated, read-only handle on the compact runtime content database (schema v2): per-language
/// `text_<language>(verse_id, text)` tables plus provenance ranges. Structure lives in the catalog.
class ContentDatabase {
  ContentDatabase._(this.db, this.meta, this.completeLanguages, this._provenance);

  final Database db;
  final Map<String, String> meta;

  /// Languages declared served by this release AND whose text table exists. Only these are offered.
  final Set<String> completeLanguages;
  final Map<String, List<ProvenanceRange>> _provenance;

  /// SHA-256 of the ascending verse-ID layout this database (and any matching catalog) is built for.
  String get contract => meta['verse_order_sha256'] ?? '';

  static ContentDatabase open(String path) {
    if (!File(path).existsSync()) {
      throw ContentException(ContentErrorKind.missing, 'No content database at $path');
    }
    final Database db = sqlite3.open(path, mode: OpenMode.readOnly);
    try {
      final tables = {
        for (final r in db.select("SELECT name FROM sqlite_master WHERE type = 'table'")) r['name'] as String
      };
      if (!tables.contains('content_meta')) {
        throw ContentException(ContentErrorKind.wrongKind, 'Not a schema-v2 content database (no content_meta)');
      }
      final meta = {for (final r in db.select('SELECT key, value FROM content_meta')) r['key'] as String: r['value'] as String};
      if (meta['kind'] != 'content' || meta['schema_version'] != '2') {
        throw ContentException(ContentErrorKind.wrongKind,
            'Expected content schema 2, found kind=${meta['kind']} schema=${meta['schema_version']}');
      }
      final served = (meta['served_languages'] ?? '').split(',').where((l) => l.isNotEmpty);
      final complete = {
        for (final l in served)
          if (supportedLanguages.containsKey(l) && tables.contains(supportedLanguages[l])) l
      };
      final provenance = <String, List<ProvenanceRange>>{};
      for (final r in db.select(
          'SELECT language, first_verse_id, last_verse_id, source, quality_tier FROM text_provenance ORDER BY language, first_verse_id')) {
        provenance.putIfAbsent(r['language'] as String, () => []).add(ProvenanceRange(
            r['first_verse_id'] as int, r['last_verse_id'] as int, r['source'] as String, r['quality_tier'] as String));
      }
      return ContentDatabase._(db, meta, complete, provenance);
    } on SqliteException catch (e) {
      db.close();
      throw ContentException(ContentErrorKind.notSqlite, 'Not a usable SQLite database: ${e.message}');
    } catch (_) {
      db.close();
      rethrow;
    }
  }

  /// Source and quality tier of one verse in one language, from the range table (null if unknown).
  ProvenanceRange? provenanceOf(String language, int verseId) {
    final ranges = _provenance[language];
    if (ranges == null) return null;
    var lo = 0, hi = ranges.length - 1;
    while (lo <= hi) {
      final mid = (lo + hi) >> 1;
      final r = ranges[mid];
      if (verseId < r.firstVerseId) {
        hi = mid - 1;
      } else if (verseId > r.lastVerseId) {
        lo = mid + 1;
      } else {
        return r;
      }
    }
    return null;
  }

  void dispose() => db.close();
}
