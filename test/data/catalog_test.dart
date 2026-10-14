import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/data/content/catalog.dart';
import 'package:scriptures_reader_mobile/data/content/content_database.dart';
import 'package:sqlite3/sqlite3.dart';

String makeCatalog({String contract = 'abc'}) {
  final path = '${Directory.systemTemp.createTempSync().path}/catalog.db';
  final db = sqlite3.open(path);
  db.execute('CREATE TABLE catalog_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)');
  db.execute("INSERT INTO catalog_meta VALUES ('verse_order_sha256', '$contract'), ('served_languages', 'english,spanish')");
  db.execute('CREATE TABLE volumes (volume_id INTEGER PRIMARY KEY, key TEXT, sort_order INTEGER, first_verse_id INTEGER, last_verse_id INTEGER, book_count INTEGER)');
  db.execute("INSERT INTO volumes VALUES (1,'ot',1,1,5,1),(3,'bom',2,6,8,1)");
  db.execute('CREATE TABLE books (book_id INTEGER PRIMARY KEY, volume_id INTEGER, canonical_name TEXT, sort_order INTEGER, first_verse_id INTEGER, last_verse_id INTEGER, chapter_count INTEGER, verse_count INTEGER)');
  db.execute("INSERT INTO books VALUES (1,1,'Alpha Book',1,1,5,2,5),(2,3,'Beta Book',2,6,8,1,3)");
  db.execute('CREATE TABLE chapters (book_id INTEGER, chapter INTEGER, first_verse_id INTEGER, last_verse_id INTEGER)');
  db.execute('INSERT INTO chapters VALUES (1,1,1,3),(1,2,4,5),(2,1,6,8)');
  for (final l in ['english', 'spanish']) {
    db.execute('CREATE TABLE volume_names_$l (volume_id INTEGER PRIMARY KEY, name TEXT, short_name TEXT, source TEXT, citation TEXT)');
    db.execute('CREATE TABLE book_names_$l (book_id INTEGER PRIMARY KEY, name TEXT, short_name TEXT, long_name TEXT, source TEXT, long_source TEXT)');
    db.execute('CREATE TABLE book_aliases_$l (alias TEXT PRIMARY KEY, book_id INTEGER)');
  }
  db.execute("INSERT INTO volume_names_english VALUES (1,'Old Testament','OT','legacy_lds',NULL),(3,'Book of Mormon','BoM','legacy_lds',NULL)");
  db.execute("INSERT INTO volume_names_spanish VALUES (1,'Antiguo Testamento',NULL,'manual','https://example.test'),(3,'Libro de Mormón','LM','legacy_spanish',NULL)");
  db.execute("INSERT INTO book_names_english VALUES (1,'Alpha Book','Alpha','The Long Alpha','application_db','legacy_lds'),(2,'Beta Book','Beta',NULL,'application_db',NULL)");
  db.execute("INSERT INTO book_names_spanish VALUES (1,'Libro Alfa','Alfa',NULL,'application_db',NULL),(2,'Libro Beta','Beta',NULL,'application_db',NULL)");
  db.execute("INSERT INTO book_aliases_english VALUES ('alpha book',1),('alpha',1),('beta book',2)");
  db.execute("INSERT INTO book_aliases_spanish VALUES ('libro alfa',1),('alfa',1),('libro beta',2)");
  db.close();
  return path;
}

void main() {
  test('loads names per language and resolves ids to books and chapters', () {
    final c = Catalog.load(makeCatalog(), contract: 'abc');
    expect(c.languages, ['english', 'spanish']);
    expect(c.books('spanish').map((b) => b.name), ['Libro Alfa', 'Libro Beta']);
    expect(c.volumes('spanish').first.name, 'Antiguo Testamento');
    expect(c.bookOfVerse(4)!.canonicalName, 'Alpha Book');
    expect(c.chapterOfVerse(4)!.chapter, 2);
    expect(c.bookOfVerse(999), isNull);
  });

  test('navigation crosses book boundaries from id ranges', () {
    final c = Catalog.load(makeCatalog(), contract: 'abc');
    expect(c.nextChapter(c.chapterOfVerse(5)!)!.bookId, 2);          // Alpha Book 2 -> Beta Book 1
    expect(c.previousChapter(c.chapterOfVerse(6)!)!.chapter, 2);     // Beta Book 1 -> Alpha Book 2
    expect(c.nextChapter(c.chapterOfVerse(8)!), isNull);
    expect(c.previousChapter(c.chapterOfVerse(1)!), isNull);
  });

  test('alias resolution: active language, then English, then other languages', () {
    final c = Catalog.load(makeCatalog(), contract: 'abc');
    expect(c.resolve('Alfa', language: 'spanish')!.canonicalName, 'Alpha Book');
    expect(c.resolve('alpha book', language: 'spanish')!.canonicalName, 'Alpha Book');  // English fallback
    expect(c.resolve('Libro Beta', language: 'english')!.canonicalName, 'Beta Book');   // other language
    expect(c.resolve('nonsense', language: 'spanish'), isNull);
  });

  test('a catalog built for a different verse-id contract is refused', () {
    expect(() => Catalog.load(makeCatalog(contract: 'zzz'), contract: 'abc'),
        throwsA(isA<ContentException>().having((e) => e.kind, 'kind', ContentErrorKind.wrongKind)));
  });

  test('verse numbers, localized references and chapter ranges derive from the id ranges', () {
    final c = Catalog.load(makeCatalog(), contract: 'abc');
    expect(c.verseNumber(5), 2); // Alpha Book 2:2
    expect(c.reference(5, 'spanish'), 'Libro Alfa 2:2');
    expect(c.shortReference(5, 'english'), 'Alpha 2:2');
    expect(c.reference(999, 'english'), isNull);
    expect(c.chapterRange(2, 1)!.lastVerseId, 8);
    expect(c.chapterRange(2, 2), isNull);
    expect(c.chapterOfVerse(1)!.firstVerseId, 1);
    expect(c.chapterOfVerse(8)!.chapter, 1);
    expect(c.bookOfVerse(0), isNull);
  });
}
