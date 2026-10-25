import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../data/content/content_repository.dart';
import '../data/user/user_store.dart';
import 'passage_selection.dart';

/// Exact references, including gaps: "Revelation 12:3–4, 11, 13–17".
String citationFor(List<Passage> passages) {
  if (passages.isEmpty) return '';
  final runs = passageRuns(passages);
  final chapters = <String>[];
  Passage? previous;
  for (final run in runs) {
    final first = run.first;
    if (previous != null &&
        previous.bookId == first.bookId &&
        previous.chapter == first.chapter) {
      chapters[chapters.length - 1] += ', ${runLabel(run)}';
    } else {
      chapters.add(
        run.length == 1
            ? first.reference
            : '${first.book} ${first.chapter}:${runLabel(run)}',
      );
    }
    previous = first;
  }
  return chapters.join('; ');
}

/// Copy exact passages with verse boundaries and explicit gaps between runs.
String formatForCopy(List<Passage> passages, {bool withReference = true}) {
  final sorted = canonicalPassages(passages);
  if (sorted.length <= 1) {
    final body = sorted.map((p) => p.text.trim()).join(' ');
    return withReference ? '“$body” — ${citationFor(sorted)}' : body;
  }
  return passageRuns(sorted)
      .map((run) {
        final body = run.map((p) => '${p.verse} ${p.text.trim()}').join('\n');
        return withReference ? '${citationFor(run)}\n$body' : body;
      })
      .join('\n\n[…]\n\n');
}

Future<void> copyText(BuildContext context, String text, {String message = 'Copied'}) async {
  await Clipboard.setData(ClipboardData(text: text));
  if (context.mounted) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message), duration: const Duration(seconds: 2)));
  }
}

/// Add or edit a note for one verse.
Future<void> showNoteEditor(BuildContext context, UserStore user, int verseId, String reference, {Note? existing}) {
  final controller = TextEditingController(text: existing?.text ?? '');
  return showDialog<void>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(existing == null ? 'Note on $reference' : 'Edit note on $reference'),
      content: SizedBox(
        width: 480,
        child: TextField(
          controller: controller,
          autofocus: true,
          minLines: 4,
          maxLines: 10,
          decoration: const InputDecoration(hintText: 'Write what you noticed or want to remember'),
        ),
      ),
      actions: [
        if (existing != null)
          TextButton(
            onPressed: () {
              user.deleteNote(existing.id);
              Navigator.pop(ctx);
            },
            child: const Text('Delete'),
          ),
        TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
        FilledButton(
          onPressed: () {
            if (controller.text.trim().isEmpty) return;
            existing == null ? user.addNote(verseId, controller.text) : user.updateNote(existing.id, controller.text);
            Navigator.pop(ctx);
          },
          child: const Text('Save'),
        ),
      ],
    ),
  );
}

/// Verse ID of "<book> <chapter>:<verse>" using the catalog; null when the book or numbers do not exist.
int? verseIdOf(ContentRepository repo, String bookName, int chapter, int verse) {
  final book = repo.catalog.resolve(bookName, language: 'english');
  if (book == null) return null;
  final range = repo.catalog.chapterRange(book.id, chapter);
  if (range == null || verse < 1 || verse > range.verseCount) return null;
  return range.firstVerseId + verse - 1;
}
