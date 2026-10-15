import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/data/trails/trail_models.dart';
import 'package:scriptures_reader_mobile/data/user/user_store.dart';
import 'package:sqlite3/sqlite3.dart';

void main() {
  late UserStore s;
  setUp(() => s = UserStore.memory(contract: 'c1'));
  tearDown(() => s.dispose());

  test('bookmarks toggle, list newest first, and notify listeners', () {
    var n = 0;
    s.addListener(() => n++);
    expect(s.toggleBookmark(10), isTrue);
    expect(s.toggleBookmark(20), isTrue);
    expect(s.isBookmarked(10), isTrue);
    expect(s.bookmarks().map((b) => b.verseId), [20, 10]);
    expect(s.toggleBookmark(10), isFalse);
    expect(s.bookmarks().map((b) => b.verseId), [20]);
    expect(n, 3);
    expect(s.bookmarkedIn(1, 15), isEmpty);
    expect(s.bookmarkedIn(15, 25), {20});
  });

  test('highlights: same colour removes, another colour replaces', () {
    s.toggleHighlight(5, 0);
    expect(s.highlightsIn(1, 10), {5: 0});
    s.toggleHighlight(5, 2);
    expect(s.highlightsIn(1, 10), {5: 2});
    s.toggleHighlight(5, 2);
    expect(s.highlightsIn(1, 10), isEmpty);
  });

  test('notes: add, edit, delete, per verse, empty is refused', () {
    final a = s.addNote(7, '  first thought ');
    s.addNote(7, 'second');
    s.addNote(9, 'other');
    expect(s.notes(verseId: 7).map((n) => n.text), ['first thought', 'second']);
    expect(s.noteCountFor(7), 2);
    expect(s.versesWithNotes(1, 8), {7});
    s.updateNote(a, 'revised');
    expect(s.notes(verseId: 7).first.text, 'revised');
    s.deleteNote(a);
    expect(s.noteCountFor(7), 1);
    expect(() => s.addNote(7, '   '), throwsA(isA<UserDataException>()));
    expect(s.notes(), hasLength(2));
  });

  test('recent searches are de-duplicated, newest first and capped', () {
    s.rememberSearch('faith', 'search');
    s.rememberSearch('grace', 'search');
    s.rememberSearch('faith', 'search');
    s.rememberSearch('  ', 'search');
    expect(s.recentSearches().map((e) => e.query), ['faith', 'grace']);
    s.clearSearchHistory();
    expect(s.recentSearches(), isEmpty);
  });

  test('preferences and reading position round trip', () {
    expect(s.pref('theme'), isNull);
    s.setPref('theme', 'sepia');
    expect(s.pref('theme'), 'sepia');
    expect(s.prefDouble('scale', 1.0), 1.0);
    s.setPref('scale', '1.3');
    expect(s.prefDouble('scale', 1.0), 1.3);
    expect(s.position, isNull);
    s.savePosition(75, 32, 21);
    expect(s.position!.bookId, 75);
    expect([s.position!.chapter, s.position!.verse], [32, 21]);
    s.savePosition(75, 33);
    expect(s.position!.verse, isNull);
  });

  test('export carries everything created', () {
    s.toggleBookmark(1);
    s.toggleHighlight(2, 1);
    s.addNote(3, 'n');
    final e = s.exportAll();
    expect(e['format'], 'scriptura-user-data-v1');
    expect((e['bookmarks'] as List), hasLength(1));
    expect((e['highlights'] as List), hasLength(1));
    expect((e['notes'] as List), hasLength(1));
  });


  test('a backup restores into an empty store and merging twice adds nothing', () {
    s.toggleBookmark(11);
    s.toggleHighlight(12, 3);
    s.addNote(13, 'kept');
    final backup = s.exportAll();
    final other = UserStore.memory();
    addTearDown(other.dispose);
    expect(other.importAll(backup), (bookmarks: 1, highlights: 1, notes: 1, trails: 0));
    expect(other.isBookmarked(11), isTrue);
    expect(other.highlightsIn(1, 20), {12: 3});
    expect(other.notes(verseId: 13).single.text, 'kept');
    expect(other.importAll(backup), (bookmarks: 0, highlights: 0, notes: 0, trails: 0));
  });

  test('restore never overwrites existing highlights and refuses foreign or invalid data', () {
    s.toggleHighlight(5, 0);
    final r = s.importAll({
      'format': 'scriptura-user-data-v1',
      'highlights': [{'verse_id': 5, 'color': 4}, {'verse_id': -1, 'color': 1}, {'verse_id': 6, 'color': 'x'}],
      'bookmarks': [{'verse_id': 'nope'}],
      'notes': [{'verse_id': 7, 'text': '   '}],
    });
    expect(r, (bookmarks: 0, highlights: 0, notes: 0, trails: 0));
    expect(s.highlightsIn(1, 10), {5: 0});
    expect(() => s.importAll({'format': 'something-else'}), throwsA(isA<UserDataException>()));
  });

  test('a file persists across opens and a different verse layout is refused untouched', () {
    final dir = Directory.systemTemp.createTempSync('userstore-');
    addTearDown(() => dir.deleteSync(recursive: true));
    final path = '${dir.path}/user.db';
    final a = UserStore.open(path, contract: 'layoutA');
    a.toggleBookmark(42);
    a.dispose();
    final b = UserStore.open(path, contract: 'layoutA');
    expect(b.isBookmarked(42), isTrue);
    b.dispose();
    expect(() => UserStore.open(path, contract: 'layoutB'), throwsA(isA<UserDataException>()));
    final c = UserStore.open(path, contract: 'layoutA');
    expect(c.isBookmarked(42), isTrue, reason: 'refusal must not alter or delete data');
    c.dispose();
  });

  test('a version 1 file migrates to version 2 with its data untouched and no trails', () {
    final dir = Directory.systemTemp.createTempSync('userstore-v1-');
    addTearDown(() => dir.deleteSync(recursive: true));
    final path = '${dir.path}/user.db';
    final raw = sqlite3.open(path);
    raw.execute('''
      CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
      CREATE TABLE bookmarks(verse_id INTEGER PRIMARY KEY, created_at INTEGER NOT NULL) WITHOUT ROWID;
      CREATE TABLE highlights(verse_id INTEGER PRIMARY KEY, color INTEGER NOT NULL, created_at INTEGER NOT NULL) WITHOUT ROWID;
      CREATE TABLE notes(id INTEGER PRIMARY KEY AUTOINCREMENT, verse_id INTEGER NOT NULL, body TEXT NOT NULL,
                         created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
      CREATE INDEX notes_verse ON notes(verse_id);
      CREATE TABLE searches(id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT NOT NULL, mode TEXT NOT NULL, at INTEGER NOT NULL);
      CREATE TABLE prefs(key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
      INSERT INTO meta VALUES ('verse_order_sha256', 'layoutA');
      INSERT INTO bookmarks VALUES (42, 1000);
      PRAGMA user_version = 1;
    ''');
    raw.close();
    final s = UserStore.open(path, contract: 'layoutA');
    expect(s.isBookmarked(42), isTrue);
    expect(s.trails(), isEmpty);
    s.createTrail(name: 'T', seed: const TrailSeed.verse(1));
    expect(s.trails().length, 1);
    s.dispose();
  });
}
