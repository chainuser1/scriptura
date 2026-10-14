import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/data/answers/answers_store.dart';
import 'package:sqlite3/sqlite3.dart';

void main() {
  late Directory dir;
  late String path;

  setUp(() {
    dir = Directory.systemTemp.createTempSync('answers-');
    path = '${dir.path}/answers.db';
    final db = sqlite3.open(path);
    db.execute('''
      CREATE TABLE question(q_id TEXT PRIMARY KEY, kind TEXT NOT NULL);
      CREATE TABLE question_text(q_id TEXT NOT NULL, language TEXT NOT NULL, text TEXT NOT NULL, PRIMARY KEY(q_id, language));
      CREATE TABLE verse_question(verse_id INTEGER NOT NULL, q_id TEXT NOT NULL, rank INTEGER NOT NULL, score REAL NOT NULL,
                                  explicit INTEGER NOT NULL, PRIMARY KEY(verse_id, rank));
      INSERT INTO question VALUES ('Q1','doctrine'),('Q2','doctrine');
      INSERT INTO question_text VALUES ('Q1','english','What is faith?'),('Q1','spanish','¿Qué es la fe?'),('Q2','english','How do I pray?');
      INSERT INTO verse_question VALUES (100,'Q1',0,0.9,1),(100,'Q2',1,0.8,0);
    ''');
    db.close();
  });
  tearDown(() => dir.deleteSync(recursive: true));

  test('questions come in the reader\'s language where a clean translation exists, otherwise English', () {
    final s = AnswersStore.tryOpen(path)!;
    final en = s.forVerse(100);
    expect(en.map((q) => q.text), ['What is faith?', 'How do I pray?']);
    expect(en.first.curated, isTrue);
    expect(en.last.curated, isFalse);
    expect(s.forVerse(100, language: 'spanish').map((q) => q.text), ['¿Qué es la fe?', 'How do I pray?']);
    expect(s.hasQuestions(100), isTrue);
    expect(s.hasQuestions(101), isFalse);
    s.dispose();
  });

  test('a missing or unreadable pack opens as null, never throws', () {
    expect(AnswersStore.tryOpen('${dir.path}/nope.db'), isNull);
    File('${dir.path}/junk.db').writeAsStringSync('not sqlite');
    expect(AnswersStore.tryOpen('${dir.path}/junk.db'), isNull);
  });
}
