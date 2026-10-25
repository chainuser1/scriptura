import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app/nav_state.dart';
import 'package:scriptures_reader_mobile/app/passage_selection.dart';
import 'package:scriptures_reader_mobile/app/verse_tools.dart';
import 'package:scriptures_reader_mobile/data/content/content_repository.dart';
import 'package:scriptures_reader_mobile/features/search/result_groups.dart';

Passage verse(int v, {int book = 1, int chapter = 12}) => Passage(
      verseId: book * 10000 + chapter * 100 + v,
      text: 'Text for verse $v.',
      reference: '${book == 1 ? 'Revelation' : 'Zechariah'} $chapter:$v',
      shortened: '$chapter:$v',
      book: book == 1 ? 'Revelation' : 'Zechariah',
      bookId: book,
      chapter: chapter,
      verse: v,
      language: 'english',
      requestedLanguage: 'english',
      source: 'synthetic',
      qualityTier: 'test',
    );

void main() {
  test(
      'the Revelation example keeps exact runs and the strongest ranking anchor',
      () {
    final ranked = [
      verse(17),
      verse(7, book: 2, chapter: 5),
      ...[13, 14, 3, 4, 11, 15, 16].map(verse)
    ];
    final groups = groupSearchPassages(ranked);
    expect(groups, hasLength(2));
    expect(groups.first.anchor.verse, 17);
    expect(groups.first.entry.verse, 13);
    expect(groups.first.passages.map((p) => p.verse),
        [3, 4, 11, 13, 14, 15, 16, 17]);
    expect(citationFor(groups.first.passages), 'Revelation 12:3–4, 11, 13–17');
    expect(citationFor(groups.last.passages), 'Zechariah 5:7');
    expect(groups.first.atRun(1).entry.verse, 11);
    expect(groups.first.atRun(1).passages, groups.first.passages);
  });

  test('all returned chapter matches join one card regardless of rank distance',
      () {
    final ranked = [
      verse(3),
      ...List.generate(8, (i) => verse(i + 1, book: 2, chapter: i + 1)),
      verse(11),
      verse(4)
    ];
    final groups = groupSearchPassages(ranked);
    expect(groups.first.passages.map((p) => p.verse), [3, 4, 11]);
    expect(groups, hasLength(9));
    expect(groups.first.anchor.verse, 3);
    expect(groups.expand((g) => g.passages).length, ranked.length);
    expect(groups.skip(1).take(8).map((g) => g.anchor.chapter),
        List.generate(8, (i) => i + 1));
  });

  test('chapter cards follow their strongest match, not canonical book order',
      () {
    final ranked = [
      verse(7, book: 2, chapter: 5),
      verse(17),
      verse(18, chapter: 17),
      verse(13),
      verse(7)
    ];
    final groups = groupSearchPassages(ranked);
    expect(groups.map((g) => g.anchor.verse), [7, 17, 18]);
    expect(groups[1].passages.map((p) => p.verse), [7, 13, 17]);
    expect(groups[1].entry.verse, 17);
    expect(groups[2].passages.single.chapter, 17);
  });

  test('chapter grouping preserves gaps and individual display preserves rank',
      () {
    final ranked = [verse(3), verse(4), verse(11), verse(13), verse(14)];
    expect(groupSearchPassages(ranked).single.runs.map((r) => r.length),
        [2, 1, 2]);
    final separate =
        groupSearchPassages(ranked.reversed.toList(), separate: true);
    expect(separate.map((g) => g.anchor.verse), [14, 13, 11, 4, 3]);
    expect(separate.every((g) => g.passages.length == 1), isTrue);
  });

  test('duplicates are removed and chapter/book boundaries never merge', () {
    final ranked = [
      verse(3),
      verse(3),
      verse(4, chapter: 13),
      verse(4, book: 2)
    ];
    final groups = groupSearchPassages(ranked);
    expect(groups, hasLength(3));
    expect(groups.map((g) => g.anchor.verseId).toSet(), hasLength(3));
    expect(groupSearchPassages(ranked).map((g) => g.anchor.verseId),
        groups.map((g) => g.anchor.verseId));
  });

  test('copying unordered matches preserves verse boundaries and omissions',
      () {
    final matches = [17, 4, 3, 11, 13, 14, 15, 16, 3].map(verse).toList();
    final copied = formatForCopy(matches);
    expect(
        copied,
        contains(
            'Revelation 12:3–4\n3 Text for verse 3.\n4 Text for verse 4.'));
    expect(copied, contains('\n\n[…]\n\nRevelation 12:11'));
    expect(copied, isNot(contains('12:3–17')));
    expect(copied, isNot(contains('Text for verse 12.')));
    expect('Text for verse 3.'.allMatches(copied), hasLength(1));
    expect(
        formatForCopy([verse(11)]), '“Text for verse 11.” — Revelation 12:11');
  });

  test(
      'navigation carries exact matches, opens at run start, and clears stale context',
      () {
    final nav = NavState();
    final selection = PassageSelection(
        [13, 14, 15, 16, 17, 3, 4, 11].map(verse),
        anchor: verse(17));
    nav.openSearchSelection(selection);
    expect(nav.verse, 13);
    final revision = nav.readingRevision;
    nav.jumpSearchPassage(1);
    expect(nav.verse, 11);
    expect(nav.searchSelection!.passages, hasLength(8));
    expect(nav.readingRevision, greaterThan(revision));
    nav.go(Dest.search);
    expect(nav.searchSelection, isNotNull,
        reason: 'back keeps the search selection');
    nav.ask('a different query');
    expect(nav.searchSelection, isNull);
    expect(nav.verse, isNull);
    nav.openSearchSelection(selection);
    nav.setChapter(1, 13);
    expect(nav.searchSelection, isNull);
    nav.openChapter(2, 1, verseNumber: 5);
    expect(nav.verse, 5);
    expect(nav.searchSelection, isNull);
  });
}
