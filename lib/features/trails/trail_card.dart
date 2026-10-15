import 'package:flutter/material.dart';

import '../../app/looks.dart';
import '../../data/content/content_repository.dart';

/// One verse, calmly: reference, the words in the reading face, and the line that says what steered the choice.
class TrailCard extends StatelessWidget {
  const TrailCard({super.key, required this.passage, required this.prefs, required this.bookmarked, required this.onBookmark, this.hint});

  final Passage passage;
  final ReadingPrefs prefs;
  final bool bookmarked;
  final VoidCallback onBookmark;
  final String? hint;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final theme = prefs.theme;
    return Semantics(
      container: true,
      label: '${passage.reference}. ${passage.text}',
      child: Card(
        margin: EdgeInsets.zero,
        color: theme.background,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 16, 12, 20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(children: [
                Expanded(child: ExcludeSemantics(child: Text(passage.reference, style: t.titleMedium?.copyWith(color: theme.text)))),
                IconButton(
                  tooltip: bookmarked ? 'Remove bookmark' : 'Bookmark this verse',
                  onPressed: onBookmark,
                  icon: Icon(bookmarked ? Icons.bookmark : Icons.bookmark_border, color: theme.text),
                ),
              ]),
              const SizedBox(height: 8),
              Padding(
                padding: const EdgeInsets.only(right: 12),
                child: ExcludeSemantics(child: SelectableText(passage.text, style: prefs.style(color: theme.text))),
              ),
              if (hint != null) ...[
                const SizedBox(height: 16),
                Padding(
                  padding: const EdgeInsets.only(right: 12),
                  child: Text(hint!, style: t.bodySmall?.copyWith(color: theme.text.withValues(alpha: 0.75))),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
