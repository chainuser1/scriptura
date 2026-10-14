import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../data/content/content_repository.dart';
import '../data/user/user_store.dart';

/// "Alma 32:21" or, for verses in one chapter, "Alma 32:21–23".
String citationFor(List<Passage> passages) {
  if (passages.isEmpty) return '';
  final first = passages.first;
  final sameChapter = passages.every((p) => p.bookId == first.bookId && p.chapter == first.chapter);
  if (passages.length == 1) return first.reference;
  if (sameChapter) return '${first.book} ${first.chapter}:${first.verse}–${passages.last.verse}';
  return '${first.reference} – ${passages.last.reference}';
}

/// Text ready to paste into a document or message: the words, then the citation.
String formatForCopy(List<Passage> passages, {bool withReference = true}) {
  final body = passages.map((p) => p.text.trim()).join(' ');
  return withReference ? '“$body” — ${citationFor(passages)}' : body;
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
