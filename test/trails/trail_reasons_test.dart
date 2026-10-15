import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/data/trails/trail_models.dart';
import 'package:scriptures_reader_mobile/features/trails/trail_reasons.dart';

import 'trail_harness.dart';

void main() {
  final catalog = testCatalog();
  const none = TrailHitParts();

  test('with nothing known there are no reasons (never invented)', () {
    expect(buildReasons(catalog: catalog, explain: null, parts: none, sharedQuestions: const [], moodLabels: const []), isEmpty);
  });

  test('themes come first and carry the family and gene breakdown plus the honesty line', () {
    final ex = ExplainResult(
      [const FamilyShare('S', 0.4, [GeneShare('S01_salvific_divine_initiative', 0.2, 0.3)]), const FamilyShare('F', 0.2, [])],
      const [],
      const [],
      const [],
    );
    final r = buildReasons(catalog: catalog, explain: ex, parts: none, sharedQuestions: const [], moodLabels: const []);
    expect(r.first.kind, ReasonKind.themes);
    expect(r.first.text, contains('salvation'));
    expect(r.first.text, contains('divine reference'));
    expect(r.first.detail.join(' '), contains('Divine initiative'));
    expect(r.first.detail.last, contains('blend of many'));
  });

  test('mood, words, people, question, taste and variety appear only when their signal is present, at most five', () {
    final ex = ExplainResult(
      [const FamilyShare('S', 0.5, [])],
      ['D18_emotion_comfort_consolation'],
      ['believeth', 'everlasting'],
      [const SharedEntity('person:moses', 'Moses')],
    );
    final r = buildReasons(
      catalog: catalog,
      explain: ex,
      parts: const TrailHitParts(taste: 0.4, mood: 0.5, explore: true),
      sharedQuestions: ['What is faith?'],
      moodLabels: ['Comfort'],
    );
    expect(r.length, 5);
    expect(r.map((x) => x.kind).toList(), [ReasonKind.themes, ReasonKind.mood, ReasonKind.words, ReasonKind.people, ReasonKind.question]);
    expect(r[1].text, contains('Comfort'));
    expect(r[2].text, contains('believeth'));
    expect(r[3].text, contains('Moses'));
    expect(r[4].text, contains('What is faith?'));
  });

  test('taste and variety lines stand alone when there is no pair to explain', () {
    final r = buildReasons(
        catalog: catalog, explain: null, parts: const TrailHitParts(taste: 0.3, explore: true), sharedQuestions: const [], moodLabels: const []);
    expect(r.map((x) => x.kind), [ReasonKind.taste, ReasonKind.variety]);
  });
}
