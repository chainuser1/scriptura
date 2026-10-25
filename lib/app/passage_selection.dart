import '../data/content/content_repository.dart';

/// Canonical, unique passages; never fill the gaps between actual matches.
List<Passage> canonicalPassages(Iterable<Passage> passages) =>
    {for (final p in passages) p.verseId: p}.values.toList()
      ..sort((a, b) => a.verseId.compareTo(b.verseId));

List<List<Passage>> passageRuns(Iterable<Passage> passages) {
  final runs = <List<Passage>>[];
  for (final p in canonicalPassages(passages)) {
    final previous = runs.isEmpty ? null : runs.last.last;
    if (previous == null ||
        previous.bookId != p.bookId ||
        previous.chapter != p.chapter ||
        previous.verse + 1 != p.verse) {
      runs.add(<Passage>[]);
    }
    runs.last.add(p);
  }
  return runs;
}

String runLabel(List<Passage> run) => run.length == 1
    ? '${run.first.verse}'
    : '${run.first.verse}–${run.last.verse}';

/// One search result, with ranking identity distinct from its reading position.
class PassageSelection {
  factory PassageSelection(
    Iterable<Passage> members, {
    required Passage anchor,
  }) {
    final passages = canonicalPassages(members);
    if (passages.isEmpty ||
        !passages.any((p) => p.verseId == anchor.verseId) ||
        passages.any(
          (p) => p.bookId != anchor.bookId || p.chapter != anchor.chapter,
        )) {
      throw ArgumentError(
        'A search selection must contain its anchor and belong to one chapter',
      );
    }
    final runs = passageRuns(passages);
    return PassageSelection._(
      List.unmodifiable(passages),
      List.unmodifiable(runs.map((r) => List<Passage>.unmodifiable(r))),
      anchor,
      runs.indexWhere((r) => r.any((p) => p.verseId == anchor.verseId)),
    );
  }

  PassageSelection._(this.passages, this.runs, this.anchor, this.activeRun);

  final List<Passage> passages;
  final List<List<Passage>> runs;
  final Passage anchor;
  final int activeRun;
  Passage get entry => runs[activeRun].first;
  bool contains(int verseId) => passages.any((p) => p.verseId == verseId);
  bool isActive(int verseId) =>
      runs[activeRun].any((p) => p.verseId == verseId);

  PassageSelection atRun(int index) {
    RangeError.checkValidIndex(index, runs);
    return PassageSelection._(passages, runs, anchor, index);
  }
}
