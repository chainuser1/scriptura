import 'package:flutter_test/flutter_test.dart';

import 'trail_harness.dart';

void main() {
  test('moods, starters and labels are looked up by id', () {
    final c = testCatalog();
    expect(c.moods.map((m) => m.label), ['Comfort', 'Peace']);
    expect(c.mood('comfort')!.genes.single.id, 'D18_emotion_comfort_consolation');
    expect(c.moodGenes('peace'), [{'id': 'D08_emotion_peace_stillness', 'weight': 1.0}]);
    expect(c.moodGenes('nope'), isEmpty);
    expect(c.starters.single.moodId, 'comfort');
    expect(c.familyLabel('S'), 'Salvation');
    expect(c.familyLabel('Z'), 'Z');
    expect(c.geneLabel('S01_salvific_divine_initiative'), 'Divine initiative');
    expect(c.geneLabel('X99_unknown_gene'), 'Unknown gene');
  });
}
