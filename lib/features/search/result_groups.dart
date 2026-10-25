import '../../app/passage_selection.dart';
import '../../data/content/content_repository.dart';

/// A fixed neighborhood of ten final ranks, including the anchor. This matches
/// the smallest focus cohort without pulling the whole twenty-hit list forward.
/// It is anchored, not transitive: later members cannot widen the neighborhood.
const resultGroupRankWindow = 10;

List<PassageSelection> groupSearchPassages(
  List<Passage> ranked, {
  Set<int> rerankedVerseIds = const {},
  bool phrase = false,
  bool separate = false,
}) {
  final seen = <int>{};
  final hits = ranked.where((p) => seen.add(p.verseId)).toList();
  final used = <int>{};
  final phraseRuns = phrase ? passageRuns(hits) : const <List<Passage>>[];
  final groups = <PassageSelection>[];
  for (var i = 0; i < hits.length; i++) {
    final anchor = hits[i];
    if (used.contains(anchor.verseId)) continue;
    final members = <Passage>[anchor];
    if (!separate) {
      if (phrase) {
        members.addAll(
          phraseRuns.firstWhere(
            (r) => r.any((p) => p.verseId == anchor.verseId),
          ),
        );
      } else {
        for (var j = i + 1;
            j < hits.length && j < i + resultGroupRankWindow;
            j++) {
          final p = hits[j];
          if (!used.contains(p.verseId) &&
              p.bookId == anchor.bookId &&
              p.chapter == anchor.chapter &&
              rerankedVerseIds.contains(p.verseId) ==
                  rerankedVerseIds.contains(anchor.verseId)) {
            members.add(p);
          }
        }
      }
    }
    final group = PassageSelection(members, anchor: anchor);
    used.addAll(group.passages.map((p) => p.verseId));
    groups.add(group);
  }
  return groups;
}
