import '../../data/trails/trail_models.dart';
import 'trail_catalog.dart';

enum ReasonKind { themes, mood, words, people, question, taste, variety }

class Reason {
  const Reason(this.kind, this.text, {this.detail = const []});
  final ReasonKind kind;
  final String text;
  final List<String> detail;
}

/// Reasons a verse is on a trail, strongest first, at most five. Only lines whose signal is present are returned.
List<Reason> buildReasons({
  required TrailCatalog catalog,
  ExplainResult? explain,
  required TrailHitParts parts,
  required List<String> sharedQuestions,
  required List<String> moodLabels,
}) {
  final out = <Reason>[];
  String lower(String s) => s.isEmpty ? s : s[0].toLowerCase() + s.substring(1);

  if (explain != null && explain.families.isNotEmpty) {
    final top = explain.families.take(2).map((f) => lower(catalog.familyLabel(f.family))).toList();
    out.add(Reason(
      ReasonKind.themes,
      'Shares themes of ${top.join(' and ')}',
      detail: [
        for (final f in explain.families)
          if (f.genes.isNotEmpty) '${catalog.familyLabel(f.family)}: ${f.genes.map((g) => catalog.geneLabel(g.id)).join(', ')}',
        'Similarity is a blend of many features; these are the strongest.',
      ],
    ));
  }
  if (explain != null && explain.moodMatches.isNotEmpty && parts.mood > 0 && moodLabels.isNotEmpty) {
    out.add(Reason(ReasonKind.mood,
        'Matches your ${moodLabels.join(' and ')} mood: ${explain.moodMatches.map((g) => lower(catalog.geneLabel(g))).join(', ')}'));
  }
  if (explain != null && explain.sharedTerms.isNotEmpty) {
    out.add(Reason(ReasonKind.words, 'Shares the words ${explain.sharedTerms.take(4).map((w) => '“$w”').join(', ')}'));
  }
  if (explain != null && explain.sharedEntities.isNotEmpty) {
    out.add(Reason(ReasonKind.people, 'Also about ${explain.sharedEntities.map((e) => e.name.isEmpty ? e.id : e.name).join(', ')}'));
  }
  if (sharedQuestions.isNotEmpty) {
    out.add(Reason(ReasonKind.question, 'Both speak to: “${sharedQuestions.first}”'));
  }
  if (parts.taste >= 0.1) out.add(const Reason(ReasonKind.taste, 'Fits what you have liked so far'));
  if (parts.explore) out.add(const Reason(ReasonKind.variety, 'A step to the side, to show you something different'));
  return out.take(5).toList();
}
