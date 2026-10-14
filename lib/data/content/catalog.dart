import 'package:sqlite3/sqlite3.dart';

import 'content_database.dart';

class VolumeEntry {
  VolumeEntry(this.id, this.key, this.name, this.shortName, this.source, this.firstVerseId, this.lastVerseId);
  final int id, firstVerseId, lastVerseId;
  final String key, name, source;
  final String? shortName;
}

class BookRef {
  BookRef(this.id, this.volumeId, this.canonicalName, this.firstVerseId, this.lastVerseId, this.chapterCount);
  final int id, volumeId, firstVerseId, lastVerseId, chapterCount;
  final String canonicalName;
  int get verseCount => lastVerseId - firstVerseId + 1;
}

class LocalizedBook {
  LocalizedBook(this.book, this.name, this.shortName, this.longName);
  final BookRef book;
  final String name, shortName;
  final String? longName;
}

class ChapterRange {
  ChapterRange(this.bookId, this.chapter, this.firstVerseId, this.lastVerseId);
  final int bookId, chapter, firstVerseId, lastVerseId;
  int get verseCount => lastVerseId - firstVerseId + 1;
}

/// Immutable, fully in-memory navigation and naming catalog. No SQL after load; verse-ID lookups are binary searches.
/// It is the single authority for structure: book, chapter, verse number and localized references are derived here.
class Catalog {
  Catalog._(this.languages, this.contract, this._books, this._chapters, this._chapterIndex, this._names,
      this._volNames, this._aliases);

  final List<String> languages;

  /// The verse-order contract this catalog was built for; must equal the content database's.
  final String contract;
  final List<BookRef> _books; // ordered by first verse id
  final List<ChapterRange> _chapters; // ordered by first verse id
  final Map<int, ChapterRange> _chapterIndex; // bookId * 1000 + chapter
  final Map<String, List<LocalizedBook>> _names;
  final Map<String, List<VolumeEntry>> _volNames;
  final Map<String, Map<String, int>> _aliases;

  static const _allowedLanguages = {'english', 'spanish', 'tagalog', 'cebuano', 'greek', 'french', 'german', 'hebrew'};

  /// [contract] is the content database's verse_order_sha256; a catalog built for another ID layout is refused.
  static Catalog load(String path, {required String contract}) {
    final db = sqlite3.open(path, mode: OpenMode.readOnly);
    try {
      final meta = {for (final r in db.select('SELECT key, value FROM catalog_meta')) r['key'] as String: r['value'] as String};
      if (meta['verse_order_sha256'] != contract) {
        throw ContentException(ContentErrorKind.wrongKind, 'Catalog was built for a different verse-id layout');
      }
      final languages = (meta['served_languages'] ?? '').split(',').where((l) => l.isNotEmpty).toList();
      final volumeRows = [for (final r in db.select('SELECT * FROM volumes ORDER BY sort_order')) r];
      final books = [
        for (final r in db.select('SELECT * FROM books ORDER BY first_verse_id'))
          BookRef(r['book_id'] as int, r['volume_id'] as int, r['canonical_name'] as String, r['first_verse_id'] as int,
              r['last_verse_id'] as int, r['chapter_count'] as int)
      ];
      final chapters = [
        for (final r in db.select('SELECT * FROM chapters ORDER BY first_verse_id'))
          ChapterRange(r['book_id'] as int, r['chapter'] as int, r['first_verse_id'] as int, r['last_verse_id'] as int)
      ];
      final index = {for (final c in chapters) c.bookId * 1000 + c.chapter: c};
      final byId = {for (final b in books) b.id: b};
      final names = <String, List<LocalizedBook>>{};
      final volNames = <String, List<VolumeEntry>>{};
      final aliases = <String, Map<String, int>>{};
      for (final l in languages) {
        if (!_allowedLanguages.contains(l)) {
          throw ContentException(ContentErrorKind.unsupportedLanguage, 'Unknown catalog language $l');
        }
        names[l] = [
          for (final r in db.select('SELECT * FROM book_names_$l ORDER BY book_id'))
            LocalizedBook(byId[r['book_id'] as int]!, r['name'] as String, r['short_name'] as String, r['long_name'] as String?)
        ]..sort((a, b) => a.book.firstVerseId.compareTo(b.book.firstVerseId));
        volNames[l] = [
          for (final v in volumeRows)
            for (final r in db.select('SELECT * FROM volume_names_$l WHERE volume_id = ?', [v['volume_id']]))
              VolumeEntry(v['volume_id'] as int, v['key'] as String, r['name'] as String, r['short_name'] as String?,
                  r['source'] as String, v['first_verse_id'] as int, v['last_verse_id'] as int)
        ];
        aliases[l] = {for (final r in db.select('SELECT alias, book_id FROM book_aliases_$l')) r['alias'] as String: r['book_id'] as int};
      }
      return Catalog._(languages, contract, books, chapters, index, names, volNames, aliases);
    } on SqliteException catch (e) {
      throw ContentException(ContentErrorKind.notSqlite, 'Not a usable catalog: ${e.message}');
    } finally {
      db.close();
    }
  }

  List<LocalizedBook> books(String language) => _names[language] ?? _names['english']!;
  List<VolumeEntry> volumes(String language) => _volNames[language] ?? _volNames['english']!;

  BookRef? book(int bookId) {
    for (final b in _books) {
      if (b.id == bookId) return b;
    }
    return null;
  }

  BookRef? bookOfVerse(int verseId) {
    var lo = 0, hi = _books.length - 1;
    while (lo <= hi) {
      final mid = (lo + hi) >> 1;
      final b = _books[mid];
      if (verseId < b.firstVerseId) {
        hi = mid - 1;
      } else if (verseId > b.lastVerseId) {
        lo = mid + 1;
      } else {
        return b;
      }
    }
    return null;
  }

  ChapterRange? chapterOfVerse(int verseId) {
    var lo = 0, hi = _chapters.length - 1;
    while (lo <= hi) {
      final mid = (lo + hi) >> 1;
      final c = _chapters[mid];
      if (verseId < c.firstVerseId) {
        hi = mid - 1;
      } else if (verseId > c.lastVerseId) {
        lo = mid + 1;
      } else {
        return c;
      }
    }
    return null;
  }

  ChapterRange? chapterRange(int bookId, int chapter) => _chapterIndex[bookId * 1000 + chapter];

  /// Verse number within its chapter (verse ids are contiguous and numbered 1..n; verified at build time).
  int? verseNumber(int verseId) {
    final c = chapterOfVerse(verseId);
    return c == null ? null : verseId - c.firstVerseId + 1;
  }

  LocalizedBook? localizedBook(String language, int bookId) {
    for (final b in books(language)) {
      if (b.book.id == bookId) return b;
    }
    return null;
  }

  /// "Génesis 1:1" in the given language (falls back to English names if the language has no catalog).
  String? reference(int verseId, String language) => _format(verseId, language, short: false);

  /// "Gén 1:1".
  String? shortReference(int verseId, String language) => _format(verseId, language, short: true);

  String? _format(int verseId, String language, {required bool short}) {
    final c = chapterOfVerse(verseId);
    if (c == null) return null;
    final b = localizedBook(language, c.bookId);
    if (b == null) return null;
    return '${short ? b.shortName : b.name} ${c.chapter}:${verseId - c.firstVerseId + 1}';
  }

  static String _fold(String s) => s.trim().toLowerCase().replaceAll('.', '').replaceAll(RegExp(r'\s+'), ' ');

  /// Active language first, then English, then every other catalog language.
  BookRef? resolve(String input, {required String language}) {
    final key = _fold(input);
    final order = [language, 'english', ...languages.where((l) => l != language && l != 'english')];
    for (final l in order) {
      final id = _aliases[l]?[key];
      if (id != null) return book(id);
    }
    return null;
  }

  ChapterRange? nextChapter(ChapterRange c) {
    final i = _indexOfChapter(c);
    return i >= 0 && i + 1 < _chapters.length ? _chapters[i + 1] : null;
  }

  ChapterRange? previousChapter(ChapterRange c) {
    final i = _indexOfChapter(c);
    return i > 0 ? _chapters[i - 1] : null;
  }

  int _indexOfChapter(ChapterRange c) {
    var lo = 0, hi = _chapters.length - 1;
    while (lo <= hi) {
      final mid = (lo + hi) >> 1;
      final x = _chapters[mid].firstVerseId;
      if (c.firstVerseId < x) {
        hi = mid - 1;
      } else if (c.firstVerseId > x) {
        lo = mid + 1;
      } else {
        return mid;
      }
    }
    return -1;
  }
}
