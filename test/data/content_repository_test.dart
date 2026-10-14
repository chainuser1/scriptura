import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/data/content/catalog.dart';
import 'package:scriptures_reader_mobile/data/content/content_database.dart';
import 'package:scriptures_reader_mobile/data/content/content_repository.dart';
import 'package:sqlite3/sqlite3.dart';

Matcher kind(ContentErrorKind k) => throwsA(isA<ContentException>().having((e) => e.kind, 'kind', k));

const contentFixture = 'test/fixtures/content_v2_mini.db';
const catalogFixture = 'test/fixtures/catalog_mini.db';

void main() {
  late ContentDatabase db;
  late Catalog catalog;
  late ContentRepository repo;
  setUp(() {
    db = ContentDatabase.open(contentFixture);
    catalog = Catalog.load(catalogFixture, contract: db.contract);
    repo = ContentRepository(db, catalog);
  });
  tearDown(() => db.dispose());

  test('only complete languages are served', () {
    expect(repo.servedLanguages, ['english', 'greek', 'spanish']);
  });

  test('a passage carries its text, provenance and a localized reference derived from the catalog', () {
    final p = repo.getPassage(2, language: 'spanish');
    expect(p.text, 'Pasaje sintético 2: ¿cómo estás?'); // accents and ¿ unchanged
    expect(p.isFallback, isFalse);
    expect(p.source, 'synthetic_es');
    expect(p.reference, 'Libro Alfa 1:2');
    expect(p.shortened, 'Alfa 1:2');
    expect([p.book, p.bookId, p.chapter, p.verse], ['Libro Alfa', 1, 1, 2]);
    final e = repo.getPassage(5);
    expect([e.reference, e.shortened, e.chapter, e.verse], ['Alpha Book 2:2', 'Alpha 2:2', 2, 2]);
  });

  test('an incomplete or uninstalled language is not served (no half-serving)', () {
    expect(() => repo.getPassage(1, language: 'french'), kind(ContentErrorKind.unsupportedLanguage)); // 5/8
    expect(() => repo.getPassage(1, language: 'hebrew'), kind(ContentErrorKind.unsupportedLanguage)); // not installed
    expect(() => repo.getChapter(1, 1, language: 'french'), kind(ContentErrorKind.unsupportedLanguage));
  });

  test('unknown or injected language never reaches SQL', () {
    for (final bad in ['klingon', 'english; DROP TABLE text_english', '', 'ENGLISH']) {
      expect(() => repo.getPassage(1, language: bad), kind(ContentErrorKind.unsupportedLanguage));
    }
    expect(repo.getPassage(1).text, startsWith('Synthetic')); // table still there
  });

  test('unknown verse id and unknown chapter raise notFound', () {
    expect(() => repo.getPassage(9999), kind(ContentErrorKind.notFound));
    expect(() => repo.getChapter(1, 9), kind(ContentErrorKind.notFound));
  });

  test('a data hole in a complete language falls back per verse, flagged, in order', () {
    final dir = Directory.systemTemp.createTempSync('hole');
    final copy = '${dir.path}/content.db';
    File(contentFixture).copySync(copy);
    final w = sqlite3.open(copy);
    w.execute('DELETE FROM text_spanish WHERE verse_id IN (6, 7)'); // Beta Book 1:1 and 1:2
    w.close();

    final holey = ContentDatabase.open(copy);
    addTearDown(holey.dispose);
    final r = ContentRepository(holey, Catalog.load(catalogFixture, contract: holey.contract));

    final ch = r.getChapter(2, 1, language: 'spanish');
    expect(ch.map((p) => p.verse), [1, 2, 3]);
    expect(ch.map((p) => p.isFallback), [true, true, false]);
    expect(ch[0].language, 'english');
    expect(ch[0].source, 'synthetic'); // English provenance, not Spanish
    expect(ch[0].reference, 'Beta Book 1:1'); // English names for English text
    expect(ch[2].source, 'synthetic_es');
    expect(ch[2].reference, 'Libro Beta 1:3');

    final p = r.getPassage(7, language: 'spanish');
    expect(p.isFallback, isTrue);
    expect(p.requestedLanguage, 'spanish');
  });

  test('Greek (polytonic) round-trips unchanged with a Greek reference', () {
    final p = repo.getPassage(1, language: 'greek');
    expect(p.text, 'Σύνθετο κείμενο 1 ἀγάπη');
    expect(p.reference, 'Βιβλίο Άλφα 1:1');
    expect(p.isFallback, isFalse);
  });

  test('chapters are read by book id and range, in order', () {
    final ch = repo.getChapter(1, 2, language: 'english');
    expect(ch.map((p) => p.verseId), [4, 5]);
    expect(ch.map((p) => p.verse), [1, 2]);
  });

  test('books come in canonical order, localized, grouped by volume', () {
    final en = repo.listBooks();
    expect(en.map((b) => b.name), ['Alpha Book', 'Beta Book']);
    expect([en.first.chapters, en.first.verses, en.last.chapters, en.last.verses], [2, 5, 1, 3]);
    final es = repo.listBooks(language: 'spanish');
    expect(es.map((b) => b.name), ['Libro Alfa', 'Libro Beta']);
    expect(es.map((b) => b.canonicalName), ['Alpha Book', 'Beta Book']);
    expect(repo.volumes().map((v) => v.name), ['Old Testament', 'Book of Mormon']);
  });

  test('book aliases resolve across languages', () {
    expect(repo.resolveBook('alfa', language: 'spanish')!.id, 1);
    expect(repo.resolveBook('  ALPHA   book ', language: 'spanish')!.id, 1); // English fallback
    expect(repo.resolveBook('nonsense'), isNull);
  });

  test('a catalog built for another verse-id layout is refused', () {
    expect(() => Catalog.load(catalogFixture, contract: 'something-else'), kind(ContentErrorKind.wrongKind));
  });
}
