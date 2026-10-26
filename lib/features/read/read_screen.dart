import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../app/looks.dart';
import '../../app/theme.dart';
import '../../app/verse_tools.dart';
import '../../app/nav_state.dart';
import '../../app/passage_navigation.dart';
import '../../app/passage_colors.dart';
import '../../app_controller.dart';
import '../../data/content/content_repository.dart';
import '../../data/trails/trail_models.dart';
import 'reading_sheet.dart';
import '../../data/user/user_store.dart';
import '../trails/start_trail.dart';

String _label(String language) =>
    language[0].toUpperCase() + language.substring(1);

/// Book browser beside a book-style reading column. Click or right-click any verse for its actions.
class ReadScreen extends StatefulWidget {
  const ReadScreen({super.key, required this.app});
  final AppController app;

  @override
  State<ReadScreen> createState() => _ReadScreenState();
}

class _ReadScreenState extends State<ReadScreen> {
  final _markedKey = GlobalKey();
  final _scroll = ScrollController();
  int _lastReadingRevision = -1;

  AppController get app => widget.app;
  ContentRepository get repo => app.repository!;
  UserStore get user => app.user;

  ({int book, int chapter}) get _where {
    final nav = app.nav;
    if (nav.bookId != null) return (book: nav.bookId!, chapter: nav.chapter);
    final p = user.position;
    if (p != null) return (book: p.bookId, chapter: p.chapter);
    return (book: repo.listBooks(language: app.language).first.id, chapter: 1);
  }

  void _go(int book, int chapter) {
    app.nav.setChapter(book, chapter);
    _scroll.jumpTo(0);
  }

  void _step(int delta) {
    final w = _where;
    final c = repo.catalog.chapterRange(w.book, w.chapter);
    if (c == null) return;
    final n = delta > 0
        ? repo.catalog.nextChapter(c)
        : repo.catalog.previousChapter(c);
    if (n != null) _go(n.bookId, n.chapter);
  }

  void _scale(double d) => user.setPref(
    'text_scale',
    (user.prefDouble('text_scale', 1.0) + d).clamp(0.8, 1.8).toStringAsFixed(2),
  );

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: Listenable.merge([app, app.nav, user]),
      builder: (context, _) {
        final w = _where;
        final lang = app.language;
        final books = repo.listBooks(language: lang);
        final book = books.firstWhere(
          (b) => b.id == w.book,
          orElse: () => books.first,
        );
        final chapter = w.chapter.clamp(1, book.chapters);
        if (app.nav.dest == Dest.read &&
            app.nav.verse != null &&
            _lastReadingRevision != app.nav.readingRevision) {
          final revision = app.nav.readingRevision;
          _lastReadingRevision = revision;
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (!mounted || app.nav.dest != Dest.read ||
                app.nav.readingRevision != revision) {
              return;
            }
            final target = _markedKey.currentContext;
            if (target != null) {
              Scrollable.ensureVisible(
                target,
                alignment: 0.25,
                duration: MediaQuery.disableAnimationsOf(context)
                    ? Duration.zero
                    : const Duration(milliseconds: 180),
              );
            }
          });
        }
        user.savePosition(book.id, chapter, app.nav.verse);
        final wide = MediaQuery.sizeOf(context).width >= kWideBreakpoint;
        final browser = _Browser(
          app: app,
          books: books,
          currentBook: book.id,
          currentChapter: chapter,
          onPick: _go,
        );
        final reading = CallbackShortcuts(
          bindings: {
            const SingleActivator(LogicalKeyboardKey.arrowLeft): () =>
                _step(-1),
            const SingleActivator(LogicalKeyboardKey.arrowRight): () =>
                _step(1),
            const SingleActivator(
              LogicalKeyboardKey.equal,
              control: true,
            ): () =>
                _scale(0.1),
            const SingleActivator(
              LogicalKeyboardKey.minus,
              control: true,
            ): () =>
                _scale(-0.1),
          },
          child: Focus(
            autofocus: true,
            child: _Reading(
              app: app,
              book: book,
              chapter: chapter,
              scroll: _scroll,
              markedKey: _markedKey,
              onStep: _step,
              onBrowse: wide
                  ? null
                  : () => _openBrowser(context, books, book.id, chapter),
            ),
          ),
        );
        if (!wide) return reading;
        return Row(
          children: [
            SizedBox(width: 300, child: browser),
            const VerticalDivider(),
            Expanded(child: reading),
          ],
        );
      },
    );
  }

  void _openBrowser(
    BuildContext context,
    List<BookEntry> books,
    int book,
    int chapter,
  ) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => SizedBox(
        height: MediaQuery.sizeOf(ctx).height * 0.8,
        child: _Browser(
          app: app,
          books: books,
          currentBook: book,
          currentChapter: chapter,
          onPick: (b, c) {
            Navigator.pop(ctx);
            _go(b, c);
          },
        ),
      ),
    );
  }
}

class _Browser extends StatefulWidget {
  const _Browser({required this.app, required this.books, required this.currentBook, required this.currentChapter, required this.onPick});
  final AppController app;
  final List<BookEntry> books;
  final int currentBook, currentChapter;
  final void Function(int book, int chapter) onPick;

  @override
  State<_Browser> createState() => _BrowserState();
}

class _BrowserState extends State<_Browser> {
  final _currentKey = GlobalKey();
  int? _shownFor;

  AppController get app => widget.app;
  List<BookEntry> get books => widget.books;
  int get currentBook => widget.currentBook;
  int get currentChapter => widget.currentChapter;
  void Function(int, int) get onPick => widget.onPick;

  @override
  Widget build(BuildContext context) {
    if (_shownFor != currentBook) {
      _shownFor = currentBook;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        final c = _currentKey.currentContext;
        if (c != null) Scrollable.ensureVisible(c, alignment: 0.1, duration: const Duration(milliseconds: 150));
      });
    }
    final repo = app.repository!;
    final volumes = repo.volumes(language: app.language);
    final t = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.symmetric(vertical: 8),
      children: [
        for (final v in volumes)
          Builder(builder: (context) {
            final inVolume = books.where((b) => b.volumeId == v.id).toList();
            final holdsCurrent = inVolume.any((b) => b.id == currentBook);
            return ExpansionTile(
              key: ValueKey('vol-${v.id}-$holdsCurrent'),
              initiallyExpanded: holdsCurrent,
              title: Text(v.name, style: t.textTheme.titleSmall),
              children: [
                for (final b in inVolume)
                  ExpansionTile(
                    key: b.id == currentBook ? _currentKey : ValueKey('book-${b.id}'),
                    initiallyExpanded: b.id == currentBook,
                    dense: true,
                    tilePadding: const EdgeInsets.only(left: 28, right: 16),
                    title: Text(b.name, style: TextStyle(fontWeight: b.id == currentBook ? FontWeight.bold : null)),
                    subtitle: b.chapters == 1 ? null : Text('${b.chapters} chapters'),
                    children: [
                      Padding(
                        padding: const EdgeInsets.fromLTRB(28, 0, 16, 12),
                        child: Wrap(spacing: 6, runSpacing: 6, children: [
                          for (var c = 1; c <= b.chapters; c++)
                            ChoiceChip(
                              label: Text('$c'),
                              visualDensity: VisualDensity.compact,
                              selected: b.id == currentBook && c == currentChapter,
                              onSelected: (_) => onPick(b.id, c),
                            ),
                        ]),
                      ),
                    ],
                  ),
              ],
            );
          }),
      ],
    );
  }
}

/// Previous and next chapter, always within reach: two small buttons at the lower corners that rest faint, brighten when
/// touched or hovered, and step aside while the page is being scrolled so they never sit on the words you are reading.
class _FloatingFlip extends StatefulWidget {
  const _FloatingFlip({required this.scroll, required this.theme, required this.onPrevious, required this.onNext});
  final ScrollController scroll;
  final ReadingTheme theme;
  final VoidCallback? onPrevious, onNext;

  @override
  State<_FloatingFlip> createState() => _FloatingFlipState();
}

class _FloatingFlipState extends State<_FloatingFlip> {
  bool _scrolling = false, _near = false;
  Timer? _idle;
  double _last = 0;

  @override
  void initState() {
    super.initState();
    widget.scroll.addListener(_onScroll);
  }

  @override
  void didUpdateWidget(_FloatingFlip old) {
    super.didUpdateWidget(old);
    if (old.scroll != widget.scroll) {
      old.scroll.removeListener(_onScroll);
      widget.scroll.addListener(_onScroll);
    }
  }

  @override
  void dispose() {
    widget.scroll.removeListener(_onScroll);
    _idle?.cancel();
    super.dispose();
  }

  void _onScroll() {
    if (!widget.scroll.hasClients) return;
    final at = widget.scroll.offset;
    if ((at - _last).abs() < 1) return;
    _last = at;
    _idle?.cancel();
    if (!_scrolling) setState(() => _scrolling = true);
    _idle = Timer(const Duration(milliseconds: 700), () {
      if (mounted) setState(() => _scrolling = false);
    });
  }

  @override
  Widget build(BuildContext context) {
    final opacity = _scrolling ? 0.0 : (_near ? 1.0 : 0.4);
    final reduce = MediaQuery.disableAnimationsOf(context);
    Widget button(IconData icon, String tip, VoidCallback? onTap) {
      if (onTap == null) return const SizedBox(width: 48, height: 48);
      return Tooltip(
        message: tip,
        child: Material(
          color: widget.theme.background.withValues(alpha: 0.92),
          elevation: 1,
          shape: CircleBorder(side: BorderSide(color: widget.theme.text.withValues(alpha: 0.25))),
          child: InkWell(
            customBorder: const CircleBorder(),
            onTap: onTap,
            child: SizedBox(width: 48, height: 48, child: Icon(icon, color: widget.theme.text)),
          ),
        ),
      );
    }

    // Each button hit-tests on its own, so the strip between them never blocks selecting or tapping the text.
    Widget slot({required bool left, required Widget child}) => Positioned(
          left: left ? 8 : null,
          right: left ? null : 8,
          bottom: 12,
          child: IgnorePointer(
            ignoring: _scrolling,
            child: MouseRegion(
              onEnter: (_) => setState(() => _near = true),
              onExit: (_) => setState(() => _near = false),
              child: Listener(
                onPointerDown: (_) => setState(() => _near = true),
                child: AnimatedOpacity(
                  opacity: opacity,
                  duration: reduce ? Duration.zero : const Duration(milliseconds: 180),
                  child: child,
                ),
              ),
            ),
          ),
        );

    return Stack(children: [
      if (widget.onPrevious != null) slot(left: true, child: button(Icons.chevron_left, 'Previous chapter', widget.onPrevious)),
      if (widget.onNext != null) slot(left: false, child: button(Icons.chevron_right, 'Next chapter', widget.onNext)),
    ]);
  }
}

class _Reading extends StatelessWidget {
  const _Reading({
    required this.app,
    required this.book,
    required this.chapter,
    required this.scroll,
    required this.markedKey,
    required this.onStep,
    required this.onBrowse,
  });
  final AppController app;
  final BookEntry book;
  final int chapter;
  final ScrollController scroll;
  final GlobalKey markedKey;
  final void Function(int delta) onStep;
  final VoidCallback? onBrowse;

  @override
  Widget build(BuildContext context) {
    final repo = app.repository!;
    final user = app.user;
    final lang = app.language;
    final parallel = user.pref('parallel');
    final showParallel =
        parallel != null &&
        parallel != lang &&
        repo.servedLanguages.contains(parallel);
    final prefs = ReadingPrefs.of(user);
    final theme = prefs.theme;
    final widthPref = prefs.width;
    final maxWidth = showParallel
        ? 1100.0
        : const [560.0, 700.0, 880.0][widthPref.clamp(0, 2)];
    final passages = repo.getChapter(book.id, chapter, language: lang);
    final other = showParallel
        ? repo.getChapter(book.id, chapter, language: parallel)
        : const <Passage>[];
    final first = passages.first.verseId, last = passages.last.verseId;
    final highlights = user.highlightsIn(first, last);
    final bookmarks = user.bookmarkedIn(first, last);
    final noted = user.versesWithNotes(first, last);
    final marked = app.nav.verse;
    final selection = app.nav.searchSelection;
    final style = prefs.style(color: theme.text);
    final selectionColors = PassageColors(Theme.of(context).colorScheme,
        surface: theme.background, text: theme.text);

    Widget verse(Passage p, {required bool primary}) {
      final isMarked =
          primary && (selection?.contains(p.verseId) ?? (p.verse == marked));
      return _VerseRow(
        key: primary && p.verse == marked
            ? markedKey
            : ValueKey('verse-${p.verseId}-$primary'),
        passage: p,
        style: style,
        numberColor: theme.text.withValues(alpha: 0.72),
        numbers: prefs.numbers,
        cards: prefs.layout == VerseLayout.cards,
        cardColor: theme.text.withValues(alpha: 0.06),
        selectionColors: selectionColors,
        highlight: highlights[p.verseId],
        marked: isMarked,
        searchMatch: primary && (selection?.contains(p.verseId) ?? false),
        activeMatch: primary && (selection?.isActive(p.verseId) ?? false),
        bookmarked: primary && bookmarks.contains(p.verseId),
        hasNote: primary && noted.contains(p.verseId),
        onMenu: (at) => _verseMenu(context, at, p),
      );
    }

    final canPrev =
        repo.catalog.previousChapter(
          repo.catalog.chapterRange(book.id, chapter)!,
        ) !=
        null;
    final canNext =
        repo.catalog.nextChapter(
          repo.catalog.chapterRange(book.id, chapter)!,
        ) !=
        null;

    return Container(
      color: theme.background,
      child: SafeArea(
        bottom: false,
        child: Column(
          children: [
            _Header(
              app: app,
              book: book,
              chapter: chapter,
              theme: theme,
              onBrowse: onBrowse,
              passages: passages,
            ),
            if (selection != null)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Wrap(
                      spacing: 8,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: [
                        TextButton.icon(
                          onPressed: () => app.nav.go(Dest.search),
                          style: TextButton.styleFrom(
                            foregroundColor: theme.text,
                          ),
                          icon: const Icon(Icons.arrow_back),
                          label: const Text('Back to results'),
                        ),
                        IconButton(
                          tooltip: selection.passages.length > 1
                              ? 'Copy matched passages'
                              : 'Copy with reference',
                          color: theme.text,
                          icon: const Icon(Icons.copy),
                          onPressed: () => copyText(
                            context,
                            formatForCopy(selection.passages),
                            message: 'Copied with reference',
                          ),
                        ),
                      ],
                    ),
                    Text(
                      citationFor(selection.passages),
                      style: TextStyle(
                        color: theme.text,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    PassageNavigation(
                      selection: selection,
                      color: theme.text,
                      surfaceColor: theme.background,
                      onSelect: app.nav.jumpSearchPassage,
                    ),
                  ],
                ),
              ),
            Expanded(
              child: Stack(
                children: [
                  SelectionArea(
                    child: SingleChildScrollView(
                      controller: scroll,
                      padding: const EdgeInsets.fromLTRB(24, 8, 24, 48),
                      child: Center(
                        child: ConstrainedBox(
                          constraints: BoxConstraints(maxWidth: maxWidth),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Padding(
                                padding: const EdgeInsets.only(
                                  top: 16,
                                  bottom: 20,
                                ),
                                child: Text(
                                  '${book.name} $chapter',
                                  style: style.copyWith(
                                    fontSize: style.fontSize! * 1.5,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                              ),
                              for (var i = 0; i < passages.length; i++)
                                if (showParallel && i < other.length)
                                  Row(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Expanded(
                                        child: verse(
                                          passages[i],
                                          primary: true,
                                        ),
                                      ),
                                      const SizedBox(width: 12),
                                      Expanded(
                                        child: verse(other[i], primary: false),
                                      ),
                                    ],
                                  )
                                else
                                  verse(passages[i], primary: true),
                              const SizedBox(height: 24),
                              Row(
                                mainAxisAlignment:
                                    MainAxisAlignment.spaceBetween,
                                children: [
                                  TextButton.icon(
                                    onPressed: canPrev
                                        ? () => onStep(-1)
                                        : null,
                                    style: TextButton.styleFrom(
                                      foregroundColor: theme.text,
                                      disabledForegroundColor: theme.text
                                          .withValues(alpha: 0.45),
                                    ),
                                    icon: const Icon(Icons.chevron_left),
                                    label: const Text('Previous'),
                                  ),
                                  TextButton.icon(
                                    onPressed: canNext ? () => onStep(1) : null,
                                    style: TextButton.styleFrom(
                                      foregroundColor: theme.text,
                                      disabledForegroundColor: theme.text
                                          .withValues(alpha: 0.45),
                                    ),
                                    icon: const Icon(Icons.chevron_right),
                                    label: const Text('Next'),
                                    iconAlignment: IconAlignment.end,
                                  ),
                                ],
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                  _FloatingFlip(
                    scroll: scroll,
                    theme: theme,
                    onPrevious: canPrev ? () => onStep(-1) : null,
                    onNext: canNext ? () => onStep(1) : null,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _verseMenu(BuildContext context, Offset at, Passage p) async {
    final user = app.user;
    final overlay = Overlay.of(context).context.findRenderObject() as RenderBox;
    final bookmarked = user.isBookmarked(p.verseId);
    final noteCount = user.noteCountFor(p.verseId);
    final choice = await showMenu<String>(
      context: context,
      position: RelativeRect.fromRect(at & const Size(1, 1), Offset.zero & overlay.size),
      items: [
        PopupMenuItem(enabled: false, height: 28, child: Text(p.reference, style: Theme.of(context).textTheme.labelLarge)),
        const PopupMenuItem(value: 'copy_ref', child: ListTile(dense: true, leading: Icon(Icons.format_quote), title: Text('Copy with reference'))),
        const PopupMenuItem(value: 'copy', child: ListTile(dense: true, leading: Icon(Icons.copy), title: Text('Copy text'))),
        PopupMenuItem(
          value: 'bookmark',
          child: ListTile(dense: true, leading: Icon(bookmarked ? Icons.bookmark_remove : Icons.bookmark_add_outlined), title: Text(bookmarked ? 'Remove bookmark' : 'Bookmark')),
        ),
        PopupMenuItem(
          enabled: false,
          child: Wrap(crossAxisAlignment: WrapCrossAlignment.center, children: [
            const Padding(padding: EdgeInsets.only(right: 6), child: Text('Highlight')),
            for (var i = 0; i < highlightPalette.length; i++)
              Builder(
                builder: (ctx) => Tooltip(
                  message: highlightNames[i],
                  child: InkWell(
                    borderRadius: BorderRadius.circular(14),
                    onTap: () => Navigator.pop(ctx, 'hl:$i'),
                    child: Container(margin: const EdgeInsets.all(4), width: 20, height: 20, decoration: BoxDecoration(color: highlightPalette[i].withValues(alpha: 1), shape: BoxShape.circle)),
                  ),
                ),
              ),
          ]),
        ),
        PopupMenuItem(value: 'note', child: ListTile(dense: true, leading: const Icon(Icons.edit_note), title: Text(noteCount == 0 ? 'Add note' : 'Notes ($noteCount)'))),
        const PopupMenuItem(value: 'similar', child: ListTile(dense: true, leading: Icon(Icons.hub_outlined), title: Text('Similar verses'))),
        const PopupMenuItem(value: 'trail', child: ListTile(dense: true, leading: Icon(Icons.alt_route), title: Text('Start a trail from this verse'))),
        if (app.answers?.hasQuestions(p.verseId) ?? false)
          const PopupMenuItem(value: 'questions', child: ListTile(dense: true, leading: Icon(Icons.help_outline), title: Text('What this verse speaks to'))),
      ],
    );
    if (choice == null || !context.mounted) return;
    switch (choice) {
      case 'copy_ref':
        await copyText(context, formatForCopy([p]), message: 'Copied with reference');
      case 'copy':
        await copyText(context, p.text);
      case 'bookmark':
        user.toggleBookmark(p.verseId);
      case 'note':
        await _notes(context, p);
      case 'similar':
        app.nav.askSimilar(p.verseId, 'Verses similar to ${p.reference}');
      case 'trail':
        await startTrail(context, app, seed: TrailSeed.verse(p.verseId), name: p.reference);
      case 'questions':
        await _questions(context, p);
      default:
        if (choice.startsWith('hl:')) user.toggleHighlight(p.verseId, int.parse(choice.substring(3)));
    }
  }

  Future<void> _questions(BuildContext context, Passage p) async {
    final qs = app.answers?.forVerse(p.verseId, language: app.language) ?? const [];
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('What ${p.reference} speaks to'),
        content: SizedBox(
          width: 520,
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            for (final q in qs)
              ListTile(
                dense: true,
                leading: Icon(q.curated ? Icons.verified_outlined : Icons.help_outline),
                title: Text(q.text),
                onTap: () {
                  Navigator.pop(ctx);
                  app.nav.ask(q.text);
                },
              ),
            const SizedBox(height: 8),
            const Text('Tap a question to search for it. A check mark means the question set was mapped to this verse directly.'),
          ]),
        ),
        actions: [FilledButton(onPressed: () => Navigator.pop(ctx), child: const Text('Close'))],
      ),
    );
  }

  Future<void> _notes(BuildContext context, Passage p) async {
    final user = app.user;
    if (user.noteCountFor(p.verseId) == 0) {
      await showNoteEditor(context, user, p.verseId, p.reference);
      return;
    }
    await showDialog<void>(
      context: context,
      builder: (ctx) => ListenableBuilder(
        listenable: user,
        builder: (ctx, _) {
          final notes = user.notes(verseId: p.verseId);
          return AlertDialog(
            title: Text('Notes on ${p.reference}'),
            content: SizedBox(
              width: 480,
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                for (final n in notes)
                  ListTile(
                    title: Text(n.text, maxLines: 4, overflow: TextOverflow.ellipsis),
                    subtitle: Text(n.updatedAt.toLocal().toString().split('.').first),
                    onTap: () => showNoteEditor(ctx, user, p.verseId, p.reference, existing: n),
                  ),
              ]),
            ),
            actions: [
              TextButton(onPressed: () => showNoteEditor(ctx, user, p.verseId, p.reference), child: const Text('Add note')),
              FilledButton(onPressed: () => Navigator.pop(ctx), child: const Text('Done')),
            ],
          );
        },
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.app, required this.book, required this.chapter, required this.theme, required this.onBrowse, required this.passages});
  final AppController app;
  final BookEntry book;
  final int chapter;
  final ReadingTheme theme;
  final VoidCallback? onBrowse;
  final List<Passage> passages;

  @override
  Widget build(BuildContext context) {
    final user = app.user;
    final repo = app.repository!;
    final langs = repo.servedLanguages;
    final parallel = user.pref('parallel');
    final fg = theme.text;
    return Material(
      color: theme.background,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
        decoration: BoxDecoration(border: Border(bottom: BorderSide(color: fg.withValues(alpha: 0.12)))),
        child: IconTheme(
          data: IconThemeData(color: fg),
          child: DefaultTextStyle.merge(
            style: TextStyle(color: fg),
            child: LayoutBuilder(builder: (context, box) {
              final compact = box.maxWidth < 640;
              final aa = IconButton(
                tooltip: 'Reading look, text size and colour',
                icon: Text('Aa', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17, color: fg)),
                onPressed: () => showReadingSheet(context, app),
              );
              final languageItems = <PopupMenuEntry<String>>[
                const PopupMenuItem(value: 'lang:', child: Text('One language')),
                for (final l in langs.where((l) => l != app.language)) PopupMenuItem(value: 'lang:$l', child: Text('Beside: ${_label(l)}')),
              ];
              void onMore(String v) {
                if (v == 'chapter') {
                  copyText(context, '${formatForCopy(passages, withReference: false)}\n— ${book.name} $chapter', message: 'Chapter copied');
                } else if (v == 'range') {
                  _copyRange(context);
                } else if (v.startsWith('lang:')) {
                  user.setPref('parallel', v.substring(5));
                }
              }

              return Row(children: [
                if (onBrowse != null)
                  Flexible(
                    child: TextButton.icon(
                      onPressed: onBrowse,
                      icon: const Icon(Icons.menu_book_outlined),
                      label: Text('${book.name} $chapter', overflow: TextOverflow.ellipsis),
                      style: TextButton.styleFrom(foregroundColor: fg),
                    ),
                  ),
                if (onBrowse == null)
                  Flexible(
                    child: Padding(
                      padding: const EdgeInsets.only(left: 12),
                      child: Text('${book.name} $chapter', overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 16)),
                    ),
                  ),
                const Spacer(),
                if (compact) ...[
                  aa,
                  PopupMenuButton<String>(
                    tooltip: 'More',
                    onSelected: onMore,
                    itemBuilder: (_) => [
                      const PopupMenuItem(value: 'chapter', child: Text('Copy whole chapter')),
                      const PopupMenuItem(value: 'range', child: Text('Copy verses…')),
                      if (langs.length > 1) ...[const PopupMenuDivider(), ...languageItems],
                    ],
                  ),
                ] else ...[
                  if (langs.length > 1)
                    PopupMenuButton<String>(
                      tooltip: 'Show a second language beside this one',
                      icon: Icon(parallel == null || parallel.isEmpty ? Icons.vertical_split_outlined : Icons.vertical_split),
                      onSelected: onMore,
                      itemBuilder: (_) => languageItems,
                    ),
                  PopupMenuButton<String>(
                    tooltip: 'Copy',
                    icon: const Icon(Icons.copy_all_outlined),
                    onSelected: onMore,
                    itemBuilder: (_) => const [
                      PopupMenuItem(value: 'chapter', child: Text('Copy whole chapter')),
                      PopupMenuItem(value: 'range', child: Text('Copy verses…')),
                    ],
                  ),
                  aa,
                ],
              ]);
            }),
          ),
        ),
      ),
    );
  }

  Future<void> _copyRange(BuildContext context) async {
    final from = TextEditingController(text: '1');
    final to = TextEditingController(text: '${passages.length}');
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Copy verses of ${book.name} $chapter'),
        content: Row(mainAxisSize: MainAxisSize.min, children: [
          SizedBox(width: 90, child: TextField(controller: from, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'From'))),
          const Padding(padding: EdgeInsets.all(12), child: Text('to')),
          SizedBox(width: 90, child: TextField(controller: to, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'To'))),
        ]),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Copy')),
        ],
      ),
    );
    final a = int.tryParse(from.text) ?? 1, b = int.tryParse(to.text) ?? passages.length;
    from.dispose();
    to.dispose();
    if (ok != true || !context.mounted) return;
    final sel = passages.where((p) => p.verse >= a && p.verse <= b).toList();
    if (sel.isEmpty) return;
    await copyText(context, formatForCopy(sel), message: 'Copied ${citationFor(sel)}');
  }
}


/// One verse: tap, right-click, or Enter/Space when focused opens its menu; read aloud as "Verse N, <text>".
class _VerseRow extends StatefulWidget {
  const _VerseRow({
    super.key,
    required this.passage,
    required this.style,
    required this.numberColor,
    required this.numbers,
    required this.cards,
    required this.cardColor,
    required this.selectionColors,
    required this.highlight,
    required this.marked,
    this.activeMatch = false,
    this.searchMatch = false,
    required this.bookmarked,
    required this.hasNote,
    required this.onMenu,
  });
  final Passage passage;
  final TextStyle style;
  final Color numberColor, cardColor;
  final PassageColors selectionColors;
  final VerseNumbers numbers;
  final bool cards;
  final int? highlight;
  final bool marked, bookmarked, hasNote, activeMatch, searchMatch;
  final void Function(Offset globalPosition) onMenu;

  @override
  State<_VerseRow> createState() => _VerseRowState();
}

class _VerseRowState extends State<_VerseRow> {
  bool _focused = false;

  void _openFromKeyboard() {
    final box = context.findRenderObject() as RenderBox;
    widget.onMenu(
      box.localToGlobal(Offset(box.size.width * 0.5, box.size.height * 0.5)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final p = widget.passage;
    final style = widget.style;
    final scheme = Theme.of(context).colorScheme;
    final hl = widget.highlight;
    final colors = widget.selectionColors;
    final active = widget.activeMatch || !widget.searchMatch;
    final status = [
      if (widget.searchMatch) 'search match',
      if (widget.activeMatch) 'active passage',
      if (widget.bookmarked) 'bookmarked',
      if (hl != null) 'highlighted',
      if (widget.hasNote) 'has a note',
    ].join(', ');
    return Semantics(
      container: true,
      button: true,
      label: 'Verse ${p.verse}${status.isEmpty ? '' : ', $status'}',
      value: p.text,
      hint: 'Opens the verse menu',
      onTap: _openFromKeyboard,
      child: Focus(
        includeSemantics:
            false, // the Semantics above already describes this row
        onFocusChange: (f) => setState(() => _focused = f),
        onKeyEvent: (node, e) {
          if (e is KeyDownEvent &&
              (e.logicalKey == LogicalKeyboardKey.enter ||
                  e.logicalKey == LogicalKeyboardKey.space)) {
            _openFromKeyboard();
            return KeyEventResult.handled;
          }
          return KeyEventResult.ignored;
        },
        child: GestureDetector(
          excludeFromSemantics: true,
          behavior: HitTestBehavior.opaque,
          onTapUp: (d) => widget.onMenu(d.globalPosition),
          onSecondaryTapUp: (d) => widget.onMenu(d.globalPosition),
          child: Container(
            margin: EdgeInsets.symmetric(vertical: widget.cards ? 5 : 2),
            padding: widget.cards
                ? const EdgeInsets.fromLTRB(14, 10, 6, 10)
                : const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: hl == null
                  ? (widget.marked
                      ? (active ? colors.activeFill : colors.matchFill)
                      : (widget.cards ? widget.cardColor : null))
                  : highlightPalette[hl % highlightPalette.length],
              borderRadius: BorderRadius.circular(widget.cards ? 12 : 6),
              border: _focused
                  ? Border.all(color: scheme.tertiary, width: 2)
                  : widget.marked
                  ? Border.all(
                      color: colors.marker,
                      width: active ? 1.5 : 0.75,
                    )
                  : Border.all(color: Colors.transparent, width: 1.5),
            ),
            child: ExcludeSemantics(
              child: _withNumber(
                context,
                Text.rich(
                  TextSpan(
                    children: [
                      if (widget.numbers == VerseNumbers.inline)
                        TextSpan(
                          text: '${p.verse}  ',
                          style: style.copyWith(
                            fontSize: style.fontSize! * 0.62,
                            fontWeight: FontWeight.bold,
                            color: widget.numberColor,
                          ),
                        ),
                      TextSpan(text: p.text),
                      if (widget.bookmarked)
                        const WidgetSpan(
                          alignment: PlaceholderAlignment.middle,
                          child: Padding(
                            padding: EdgeInsets.only(left: 6),
                            child: Icon(Icons.bookmark, size: 15),
                          ),
                        ),
                      if (widget.hasNote)
                        const WidgetSpan(
                          alignment: PlaceholderAlignment.middle,
                          child: Padding(
                            padding: EdgeInsets.only(left: 6),
                            child: Icon(Icons.sticky_note_2_outlined, size: 15),
                          ),
                        ),
                      if (p.isFallback)
                        TextSpan(
                          text: '  [${p.language}]',
                          style: const TextStyle(
                            fontStyle: FontStyle.italic,
                            fontSize: 13,
                          ),
                        ),
                    ],
                  ),
                  style: style,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  /// Margin numbers sit in their own column; cards add a visible menu button. Inline and hidden need neither.
  Widget _withNumber(BuildContext context, Widget text) {
    final style = widget.style;
    final p = widget.passage;
    if (widget.numbers != VerseNumbers.margin && !widget.cards) return text;
    final top = style.fontSize! * (style.height! - 1) * 0.5 + style.fontSize! * 0.12;
    return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (widget.numbers == VerseNumbers.margin)
        SizedBox(
          width: 30,
          child: Padding(
            padding: EdgeInsets.only(top: top, right: 8),
            child: Text('${p.verse}', textAlign: TextAlign.right, style: style.copyWith(fontSize: style.fontSize! * 0.62, fontWeight: FontWeight.bold, color: widget.numberColor, height: 1.2)),
          ),
        ),
      Expanded(child: text),
      if (widget.cards)
        Builder(
          builder: (ctx) => IconButton(
            tooltip: 'Verse menu',
            icon: Icon(Icons.more_horiz, color: widget.numberColor),
            onPressed: () {
              final box = ctx.findRenderObject() as RenderBox;
              widget.onMenu(box.localToGlobal(box.size.center(Offset.zero)));
            },
          ),
        ),
    ]);
  }
}
