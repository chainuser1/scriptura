import 'catalog.dart';
import 'content_database.dart';

export 'content_database.dart' show supportedLanguages;

class Passage {
  Passage({
    required this.verseId,
    required this.text,
    required this.reference,
    required this.shortened,
    required this.book,
    required this.bookId,
    required this.chapter,
    required this.verse,
    required this.language,
    required this.requestedLanguage,
    required this.source,
    required this.qualityTier,
  });

  final int verseId, bookId, chapter, verse;

  /// `book` is the localized book name in [language] (the language of [text]).
  final String text, reference, shortened, book;
  final String language, requestedLanguage, source, qualityTier;
  bool get isFallback => language != requestedLanguage;
}

class BookEntry {
  BookEntry(this.id, this.volumeId, this.canonicalName, this.name, this.shortName, this.firstVerseId, this.chapters, this.verses);
  final int id, volumeId, firstVerseId, chapters, verses;
  final String canonicalName, name, shortName;
}

/// Reads text from the content database and derives everything structural (book, chapter, verse number, localized
/// references, navigation) from the catalog. Only languages declared complete by the release are served.
class ContentRepository {
  ContentRepository(this._content, this._catalog) {
    if (_content.contract.isEmpty || _content.contract != _catalog.contract) {
      throw ContentException(ContentErrorKind.wrongKind, 'Catalog and content database are built for different verse-id layouts');
    }
  }

  final ContentDatabase _content;
  final Catalog _catalog;

  Catalog get catalog => _catalog;

  /// Languages offered to users: declared complete by the content database AND present in the catalog.
  List<String> get servedLanguages => [
        for (final l in supportedLanguages.keys)
          if (_content.completeLanguages.contains(l) && _catalog.languages.contains(l)) l
      ]..sort();

  String _served(String language) {
    if (!supportedLanguages.containsKey(language) ||
        !_content.completeLanguages.contains(language) ||
        !_catalog.languages.contains(language)) {
      throw ContentException(ContentErrorKind.unsupportedLanguage, 'Language "$language" is not served (unknown or incomplete)');
    }
    return language;
  }

  Map<int, String> _texts(String language, int first, int last) {
    final table = supportedLanguages[language]!; // allowlisted, never user text
    return {
      for (final r in _content.db.select('SELECT verse_id, text FROM $table WHERE verse_id BETWEEN ? AND ?', [first, last]))
        r['verse_id'] as int: r['text'] as String
    };
  }

  Passage _make(int verseId, String text, String language, String requested) {
    final chapter = _catalog.chapterOfVerse(verseId);
    final lb = chapter == null ? null : _catalog.localizedBook(language, chapter.bookId);
    if (chapter == null || lb == null) {
      throw ContentException(ContentErrorKind.notFound, 'Verse $verseId is not in the catalog');
    }
    final verse = verseId - chapter.firstVerseId + 1;
    final prov = _content.provenanceOf(language, verseId);
    return Passage(
      verseId: verseId,
      text: text,
      reference: '${lb.name} ${chapter.chapter}:$verse',
      shortened: '${lb.shortName} ${chapter.chapter}:$verse',
      book: lb.name,
      bookId: chapter.bookId,
      chapter: chapter.chapter,
      verse: verse,
      language: language,
      requestedLanguage: requested,
      source: prov?.source ?? 'unknown',
      qualityTier: prov?.qualityTier ?? 'unknown',
    );
  }

  Passage getPassage(int verseId, {String language = 'english'}) {
    final lang = _served(language);
    final own = _texts(lang, verseId, verseId)[verseId];
    if (own != null) return _make(verseId, own, lang, language);
    if (lang != 'english') {
      final en = _texts('english', verseId, verseId)[verseId]; // data hole in a "complete" language
      if (en != null) return _make(verseId, en, 'english', language);
    }
    throw ContentException(ContentErrorKind.notFound, 'No passage with verse_id $verseId');
  }

  List<Passage> getChapter(int bookId, int chapter, {String language = 'english'}) {
    final lang = _served(language);
    final range = _catalog.chapterRange(bookId, chapter);
    if (range == null) {
      throw ContentException(ContentErrorKind.notFound, 'No chapter $chapter in book $bookId');
    }
    final own = _texts(lang, range.firstVerseId, range.lastVerseId);
    Map<int, String>? english;
    final out = <Passage>[];
    for (var id = range.firstVerseId; id <= range.lastVerseId; id++) {
      final t = own[id];
      if (t != null) {
        out.add(_make(id, t, lang, language));
        continue;
      }
      english ??= _texts('english', range.firstVerseId, range.lastVerseId);
      final en = english[id];
      if (en == null) {
        throw ContentException(ContentErrorKind.notFound, 'Verse $id has no text in $lang or english');
      }
      out.add(_make(id, en, 'english', language));
    }
    return out;
  }

  List<BookEntry> listBooks({String language = 'english'}) {
    return [
      for (final lb in _catalog.books(language))
        BookEntry(lb.book.id, lb.book.volumeId, lb.book.canonicalName, lb.name, lb.shortName, lb.book.firstVerseId,
            lb.book.chapterCount, lb.book.verseCount)
    ];
  }

  List<VolumeEntry> volumes({String language = 'english'}) => _catalog.volumes(language);

  BookRef? resolveBook(String input, {String language = 'english'}) => _catalog.resolve(input, language: language);
}
