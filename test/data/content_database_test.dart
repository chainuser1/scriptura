import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/data/content/content_database.dart';

const fixture = 'test/fixtures/content_v2_mini.db';

Matcher kind(ContentErrorKind k) => throwsA(isA<ContentException>().having((e) => e.kind, 'kind', k));

void main() {
  test('opens the v2 fixture read-only and exposes identity', () {
    final c = ContentDatabase.open(fixture);
    addTearDown(c.dispose);
    expect(c.meta['kind'], 'content');
    expect(c.meta['schema_version'], '2');
    expect(c.contract, isNotEmpty);
  });

  test('only languages served by the release (with a text table) are complete', () {
    final c = ContentDatabase.open(fixture);
    addTearDown(c.dispose);
    expect(c.completeLanguages, {'english', 'spanish', 'greek'}); // french is 5/8, hebrew absent
  });

  test('provenance comes from ranges, per language', () {
    final c = ContentDatabase.open(fixture);
    addTearDown(c.dispose);
    expect(c.provenanceOf('english', 3)!.source, 'synthetic');
    expect(c.provenanceOf('spanish', 8)!.source, 'synthetic_es');
    expect(c.provenanceOf('spanish', 9), isNull);
    expect(c.provenanceOf('klingon', 1), isNull);
  });

  test('FTS5 is available in the bundled SQLite', () {
    final c = ContentDatabase.open(fixture);
    addTearDown(c.dispose);
    final r = c.db.select("SELECT sqlite_compileoption_used('ENABLE_FTS5') AS fts5");
    expect(r.first['fts5'], 1);
  });

  test('missing file raises ContentException(missing)', () {
    expect(() => ContentDatabase.open('test/fixtures/nope.db'), kind(ContentErrorKind.missing));
  });

  test('a non-SQLite file raises ContentException(notSqlite)', () {
    final f = File('${Directory.systemTemp.path}/not_a_db.db')..writeAsStringSync('this is not sqlite');
    addTearDown(() => f.deleteSync());
    expect(() => ContentDatabase.open(f.path), kind(ContentErrorKind.notSqlite));
  });

  test('a v1-shaped database is refused as the wrong kind, not crashed on', () {
    expect(() => ContentDatabase.open('test/fixtures/content_mini.db'), kind(ContentErrorKind.wrongKind));
  });
}
