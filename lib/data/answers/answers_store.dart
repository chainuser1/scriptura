import 'dart:io';

import 'package:sqlite3/sqlite3.dart';

/// A study question a passage speaks to. [curated] questions were mapped to the verse by hand-reviewed question sets;
/// the rest are its nearest questions in the shared meaning space, kept only above a calibrated similarity.
class VerseQuestion {
  const VerseQuestion(this.id, this.text, {required this.curated, required this.score});
  final String id, text;
  final bool curated;
  final double score;
}

/// Read-only handle on the optional answers pack (`answers.db`). Absent pack means no questions are offered.
class AnswersStore {
  AnswersStore._(this._db);
  final Database _db;

  static AnswersStore? tryOpen(String path) {
    Database? db;
    try {
      if (!File(path).existsSync()) return null;
      db = sqlite3.open(path, mode: OpenMode.readOnly);
      db.select('SELECT 1 FROM verse_question LIMIT 1');
      return AnswersStore._(db);
    } on Object {
      db?.close();
      return null;
    }
  }

  /// Up to five questions for [verseId], in [language] where a clean translation exists, otherwise English.
  List<VerseQuestion> forVerse(int verseId, {String language = 'english'}) {
    final rows = _db.select(
      'SELECT v.q_id, COALESCE(l.text, e.text) AS text, v.explicit, v.score '
      'FROM verse_question v '
      'JOIN question_text e ON e.q_id = v.q_id AND e.language = \'english\' '
      'LEFT JOIN question_text l ON l.q_id = v.q_id AND l.language = ? '
      'WHERE v.verse_id = ? ORDER BY v.rank',
      [language, verseId],
    );
    return [
      for (final r in rows) VerseQuestion(r['q_id'] as String, r['text'] as String, curated: (r['explicit'] as int) == 1, score: (r['score'] as num).toDouble()),
    ];
  }

  bool hasQuestions(int verseId) => _db.select('SELECT 1 FROM verse_question WHERE verse_id = ? LIMIT 1', [verseId]).isNotEmpty;

  void dispose() => _db.close();
}
