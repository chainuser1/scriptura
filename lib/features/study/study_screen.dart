import 'dart:convert';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../../app/nav_state.dart';
import '../../app/theme.dart';
import '../../app/verse_tools.dart';
import '../../app_controller.dart';
import '../../data/content/content_repository.dart';
import '../../data/user/user_store.dart';

/// Everything the reader has made: bookmarks, highlights, notes and recent searches, with export.
class StudyScreen extends StatelessWidget {
  const StudyScreen({super.key, required this.app});
  final AppController app;

  Passage? _passage(int verseId) {
    try {
      return app.repository!.getPassage(verseId, language: app.language);
    } on Object {
      return null;
    }
  }

  String _markdown() {
    final u = app.user;
    final b = StringBuffer('# My scripture study\n\n');
    final notes = u.notes();
    if (notes.isNotEmpty) {
      b.writeln('## Notes\n');
      for (final n in notes.reversed) {
        final p = _passage(n.verseId);
        if (p == null) continue;
        b.writeln('### ${p.reference}\n');
        b.writeln('> ${p.text}\n');
        b.writeln('${n.text}\n');
      }
    }
    final marks = u.bookmarks();
    if (marks.isNotEmpty) {
      b.writeln('## Bookmarks\n');
      for (final m in marks) {
        final p = _passage(m.verseId);
        if (p != null) b.writeln('- **${p.reference}** — ${p.text}');
      }
      b.writeln();
    }
    final hl = u.highlights();
    if (hl.isNotEmpty) {
      b.writeln('## Highlights\n');
      for (final h in hl) {
        final p = _passage(h.verseId);
        if (p != null) b.writeln('- **${p.reference}** (${highlightNames[h.color % highlightNames.length]}) — ${p.text}');
      }
    }
    return b.toString();
  }

  Future<void> _backup(BuildContext context) async {
    final json = const JsonEncoder.withIndent('  ').convert(app.user.exportAll());
    try {
      final saved = await FilePicker.saveFile(
          fileName: 'scriptura-backup.json', bytes: utf8.encode(json), mimeType: 'application/json', dialogTitle: 'Save a backup of your notes, bookmarks and highlights');
      if (saved == null && context.mounted) await copyText(context, json, message: 'Backup copied to the clipboard instead');
    } on Object {
      if (context.mounted) await copyText(context, json, message: 'Backup copied to the clipboard');
    }
  }

  Future<void> _restore(BuildContext context) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      final picked = await FilePicker.pickFiles(type: FileType.custom, allowedExtensions: const ['json']);
      final file = picked.firstOrNull;
      if (file == null) return;
      final path = file.path;
      if (path == null) return;
      final bytes = await File(path).readAsBytes();
      final data = (jsonDecode(utf8.decode(bytes)) as Map).cast<String, Object?>();
      final books = app.repository!.listBooks();
      final r = app.user.importAll(data, maxVerseId: books.last.firstVerseId + books.last.verses - 1);
      messenger.showSnackBar(SnackBar(
        content: Text('Restored ${r.notes} notes, ${r.bookmarks} bookmarks and ${r.highlights} highlights. Nothing was overwritten.'),
      ));
    } on UserDataException catch (e) {
      messenger.showSnackBar(SnackBar(content: Text('Could not restore: ${e.message}')));
    } on Object {
      messenger.showSnackBar(const SnackBar(content: Text('Could not read that file as a Scriptura backup.')));
    }
  }

  Future<void> _export(BuildContext context) async {
    final md = _markdown();
    final bytes = utf8.encode(md);
    try {
      final saved = await FilePicker.saveFile(fileName: 'my-scripture-study.md', bytes: bytes, mimeType: 'text/markdown', dialogTitle: 'Save your study notes');
      if (saved == null && context.mounted) await copyText(context, md, message: 'Copied to the clipboard instead');
    } on Object {
      if (context.mounted) await copyText(context, md, message: 'Copied to the clipboard');
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: Listenable.merge([app, app.user]),
      builder: (context, _) {
        return DefaultTabController(
          length: 4,
          child: Column(
            children: [
              Material(
                color: Theme.of(context).colorScheme.surface,
                child: Row(children: [
                  const Expanded(
                    child: TabBar(isScrollable: true, tabAlignment: TabAlignment.start, tabs: [
                      Tab(text: 'Bookmarks'),
                      Tab(text: 'Highlights'),
                      Tab(text: 'Notes'),
                      Tab(text: 'Recent searches'),
                    ]),
                  ),
                  Padding(
                    padding: const EdgeInsets.only(right: 12),
                    child: PopupMenuButton<String>(
                      tooltip: 'Export and backup',
                      onSelected: (v) {
                        switch (v) {
                          case 'md':
                            _export(context);
                          case 'backup':
                            _backup(context);
                          case 'restore':
                            _restore(context);
                        }
                      },
                      itemBuilder: (_) => const [
                        PopupMenuItem(value: 'md', child: ListTile(dense: true, leading: Icon(Icons.description_outlined), title: Text('Export as Markdown'))),
                        PopupMenuItem(value: 'backup', child: ListTile(dense: true, leading: Icon(Icons.save_alt), title: Text('Back up everything'))),
                        PopupMenuItem(value: 'restore', child: ListTile(dense: true, leading: Icon(Icons.restore), title: Text('Restore from a backup…'))),
                      ],
                      child: const Padding(
                        padding: EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                        child: Row(mainAxisSize: MainAxisSize.min, children: [Icon(Icons.ios_share), SizedBox(width: 8), Text('Export & backup')]),
                      ),
                    ),
                  ),
                ]),
              ),
              const Divider(),
              Expanded(
                child: TabBarView(children: [
                  _list(context, [for (final b in app.user.bookmarks()) _Entry(b.verseId)], 'No bookmarks yet', 'Open any verse’s menu while reading and choose Bookmark.'),
                  _list(context, [for (final h in app.user.highlights()) _Entry(h.verseId, color: h.color)], 'No highlights yet', 'Choose a colour from a verse’s menu.'),
                  _list(context, [for (final n in app.user.notes()) _Entry(n.verseId, note: n.text, noteId: n.id)], 'No notes yet', 'Add a note from a verse’s menu.'),
                  _searches(context),
                ]),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _list(BuildContext context, List<_Entry> entries, String emptyTitle, String emptyHint) {
    if (entries.isEmpty) {
      return Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Icon(Icons.collections_bookmark_outlined, size: 40),
          const SizedBox(height: 12),
          Text(emptyTitle, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 4),
          Text(emptyHint),
        ]),
      );
    }
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 900),
        child: ListView(
          padding: const EdgeInsets.symmetric(vertical: 8),
          children: [
            for (final e in entries)
              Builder(builder: (context) {
                final p = _passage(e.verseId);
                if (p == null) return const SizedBox.shrink();
                return ListTile(
                  key: ValueKey('study-${e.verseId}-${e.noteId ?? 0}'),
                  leading: e.color == null
                      ? null
                      : CircleAvatar(radius: 8, backgroundColor: highlightPalette[e.color! % highlightPalette.length].withValues(alpha: 1)),
                  title: Text(p.reference, style: const TextStyle(fontWeight: FontWeight.w600)),
                  subtitle: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(p.text, maxLines: 3, overflow: TextOverflow.ellipsis),
                    if (e.note != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 6),
                        child: Text(e.note!, style: TextStyle(color: Theme.of(context).colorScheme.primary)),
                      ),
                  ]),
                  isThreeLine: true,
                  onTap: () => app.nav.openChapter(p.bookId, p.chapter, verseNumber: p.verse),
                  trailing: PopupMenuButton<String>(
                    tooltip: 'More',
                    onSelected: (v) {
                      switch (v) {
                        case 'open':
                          app.nav.openChapter(p.bookId, p.chapter, verseNumber: p.verse);
                        case 'copy':
                          copyText(context, formatForCopy([p]), message: 'Copied with reference');
                        case 'edit':
                          final n = app.user.notes(verseId: e.verseId).firstWhere((n) => n.id == e.noteId);
                          showNoteEditor(context, app.user, e.verseId, p.reference, existing: n);
                        case 'remove':
                          if (e.noteId != null) {
                            app.user.deleteNote(e.noteId!);
                          } else if (e.color != null) {
                            app.user.toggleHighlight(e.verseId, e.color!);
                          } else {
                            app.user.toggleBookmark(e.verseId);
                          }
                      }
                    },
                    itemBuilder: (_) => [
                      const PopupMenuItem(value: 'open', child: Text('Read in context')),
                      const PopupMenuItem(value: 'copy', child: Text('Copy with reference')),
                      if (e.noteId != null) const PopupMenuItem(value: 'edit', child: Text('Edit note')),
                      const PopupMenuItem(value: 'remove', child: Text('Remove')),
                    ],
                  ),
                );
              }),
          ],
        ),
      ),
    );
  }

  Widget _searches(BuildContext context) {
    final recent = app.user.recentSearches(limit: 50);
    if (recent.isEmpty) {
      return const Center(child: Text('Your recent searches will appear here.'));
    }
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 900),
        child: ListView(children: [
          for (final r in recent)
            ListTile(
              leading: Icon(r.mode == 'phrase' ? Icons.format_quote : Icons.search),
              title: Text(r.query),
              subtitle: Text(r.mode == 'phrase' ? 'Exact phrase' : 'Meaning'),
              onTap: () => app.nav.ask(r.query, mode: r.mode == 'phrase' ? SearchMode.phrase : SearchMode.meaning),
            ),
        ]),
      ),
    );
  }
}

class _Entry {
  _Entry(this.verseId, {this.color, this.note, this.noteId});
  final int verseId;
  final int? color, noteId;
  final String? note;
}
