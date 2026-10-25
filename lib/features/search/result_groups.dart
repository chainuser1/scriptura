import '../../app/passage_selection.dart';
import '../../data/content/content_repository.dart';

/// Group the complete returned set by chapter after ranking. Insertion order
/// preserves each chapter's strongest hit, which also selects its initial run.
List<PassageSelection> groupSearchPassages(
  List<Passage> ranked, {
  bool separate = false,
}) {
  final seen = <int>{};
  final hits = ranked.where((p) => seen.add(p.verseId));
  if (separate) {
    return [
      for (final p in hits) PassageSelection([p], anchor: p)
    ];
  }
  final chapters = <(int, int), List<Passage>>{};
  for (final p in hits) {
    (chapters[(p.bookId, p.chapter)] ??= []).add(p);
  }
  return [
    for (final members in chapters.values)
      PassageSelection(members, anchor: members.first),
  ];
}
