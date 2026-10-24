import 'package:flutter/material.dart';

import '../../app/guide_content.dart';
import '../../app/keyboard_hints.dart';
import '../../app/nav_state.dart';
import '../../app/theme.dart';
import '../../app/verse_tools.dart';
import '../../app_controller.dart';
import '../../data/content/content_repository.dart';
import '../../services/engine/answer_focus.dart';
import '../guide/guide_screen.dart';
import '../trails/starter_trails.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.app});
  final AppController app;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _ask = TextEditingController();
  bool _fallbackDialogPending = false;

  AppController get app => widget.app;
  ContentRepository get repo => app.repository!;

  @override
  void dispose() {
    _ask.dispose();
    super.dispose();
  }

  void _submit([String? text]) {
    final q = (text ?? _ask.text).trim();
    if (q.isEmpty) return;
    app.nav.ask(q);
  }

  String _greeting() {
    final h = DateTime.now().hour;
    return h < 5 ? 'Good evening' : h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
  }

  Passage? _verseOfTheDay() {
    final day = DateTime.now().difference(DateTime(DateTime.now().year)).inDays;
    for (var i = 0; i < dailyVerses.length; i++) {
      final v = dailyVerses[(day + i) % dailyVerses.length];
      final id = verseIdOf(repo, v.book, v.chapter, v.verse);
      if (id == null) continue;
      try {
        return repo.getPassage(id, language: app.language);
      } on Object {
        continue;
      }
    }
    return null;
  }

  void _explainFocusFallback() {
    if (_fallbackDialogPending || !app.focusFellBackFromDefault || app.nav.dest != Dest.home ||
        ModalRoute.of(context)?.isCurrent != true) {
      return;
    }
    _fallbackDialogPending = true;
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;
      if (!app.focusFellBackFromDefault || app.nav.dest != Dest.home || ModalRoute.of(context)?.isCurrent != true) {
        _fallbackDialogPending = false;
        return;
      }
      final explanation = app.focusChoice!.variant == FocusVariant.none
          ? 'Answer focus is not active. You can still read and search.'
          : app.focusInstalled
              ? 'Ezra is installed and has been selected instead.'
              : 'Ezra was selected instead and needs to be downloaded in Settings before Answer focus can run.';
      await showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (context) => PopScope(
          canPop: false,
          child: AlertDialog(
            title: const Text('Answer focus adjusted'),
            content: Text('Priscilla, the default Answer focus model, was too slow in this device check. $explanation'),
            actions: [TextButton(
              onPressed: () {
                app.acknowledgeFocusFallback();
                Navigator.of(context).pop();
              },
              child: const Text('Got it'),
            )],
          ),
        ),
      );
      _fallbackDialogPending = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: Listenable.merge([app, app.user, app.nav]),
      builder: (context, _) {
        _explainFocusFallback();
        final t = Theme.of(context).textTheme;
        final scheme = Theme.of(context).colorScheme;
        final pos = app.user.position;
        final book = pos == null ? null : repo.listBooks(language: app.language).where((b) => b.id == pos.bookId).firstOrNull;
        final votd = _verseOfTheDay();
        final recent = app.user.recentSearches(limit: 6);
        return SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 860),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(_greeting(), style: t.headlineMedium),
                  const SizedBox(height: 4),
                  Text('Ask a question, look up a passage, or pick up where you left off.', style: t.bodyLarge),
                  const SizedBox(height: 20),
                  TextField(
                    controller: _ask,
                    onSubmitted: _submit,
                    textInputAction: TextInputAction.search,
                    style: t.titleMedium,
                    decoration: InputDecoration(
                      hintText: 'Ask anything — or type a reference like John 3:16',
                      prefixIcon: const Icon(Icons.search),
                      suffixIcon: IconButton(tooltip: 'Search', icon: const Icon(Icons.arrow_forward), onPressed: _submit),
                      contentPadding: const EdgeInsets.symmetric(vertical: 18, horizontal: 16),
                      filled: true,
                      fillColor: scheme.surfaceContainerHighest.withValues(alpha: 0.4),
                    ),
                  ),
                  if (app.offerPriscillaDefaultSetup && !app.setupBusy) ...[
                    const SizedBox(height: 12),
                    _Notice(
                      icon: Icons.center_focus_strong_outlined,
                      text: app.missingData.difference({'colbert'}).isEmpty
                          ? 'Adding Answer focus (Priscilla). Best on Wi-Fi.'
                          : 'Setting up scripture data, search, and Answer focus (Priscilla). Best on Wi-Fi.',
                      action: 'Continue',
                      onAction: () => app.ensureData(includeFocus: true),
                    ),
                  ] else if (app.engineState == EngineState.unavailable) ...[
                    const SizedBox(height: 12),
                    _Notice(
                      icon: Icons.info_outline,
                      text: app.setupStatus != null
                          ? '${app.setupStatus} You can read in the meantime.'
                          : 'Searching by meaning needs the search data. ${app.engineProblem ?? ''}',
                      action: 'Open Settings',
                      onAction: () => app.nav.go(Dest.settings),
                    ),
                  ] else if (app.offerOptionalIndex && !app.setupBusy) ...[
                    const SizedBox(height: 12),
                    _Notice(
                      icon: Icons.tune,
                      text: 'Sharper results are available: an optional 3 GB word-level index (best on Wi-Fi).',
                      action: 'See options',
                      onAction: () => app.nav.go(Dest.settings),
                    ),
                  ] else if (app.offerAnswerFocus && !app.setupBusy) ...[
                    const SizedBox(height: 12),
                    _Notice(
                      icon: Icons.center_focus_strong_outlined,
                      text: 'Answer focus can put the passages that answer your question first. It is a download, best on Wi-Fi.',
                      action: 'See options',
                      onAction: () => app.nav.go(Dest.settings),
                    ),
                  ] else if (app.engineState == EngineState.preparing) ...[
                    const SizedBox(height: 12),
                    const _Notice(icon: Icons.hourglass_top, text: 'Search is starting. You can read in the meantime.'),
                  ],
                  const SizedBox(height: 20),
                  Text('Try asking', style: t.titleSmall),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      for (final q in starterQuestions.take(MediaQuery.sizeOf(context).width < 600 ? 4 : starterQuestions.length))
                        ActionChip(label: Text(q), onPressed: () => _submit(q)),
                    ],
                  ),
                  const SizedBox(height: 24),
                  StarterTrails(app: app),
                  const SizedBox(height: 28),
                  Wrap(
                    spacing: 16,
                    runSpacing: 16,
                    children: [
                      if (book != null)
                        _Card(
                          width: 400,
                          icon: Icons.bookmark_outline,
                          title: 'Continue reading',
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text('${book.name} ${pos!.chapter}', style: t.titleLarge),
                              const SizedBox(height: 12),
                              FilledButton.tonal(
                                onPressed: () => app.nav.openChapter(pos.bookId, pos.chapter, verseNumber: pos.verse),
                                child: const Text('Continue'),
                              ),
                            ],
                          ),
                        ),
                      if (votd != null)
                        _Card(
                          width: 400,
                          icon: Icons.wb_sunny_outlined,
                          title: 'Verse of the day',
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                votd.text,
                                style: scriptureStyle(context, scale: 0.9, color: scheme.onSurface),
                                maxLines: 6,
                                overflow: TextOverflow.ellipsis,
                              ),
                              const SizedBox(height: 8),
                              Text(votd.reference, style: t.labelLarge),
                              const SizedBox(height: 8),
                              Wrap(spacing: 8, children: [
                                TextButton(
                                  onPressed: () => app.nav.openChapter(votd.bookId, votd.chapter, verseNumber: votd.verse),
                                  child: const Text('Read in context'),
                                ),
                                TextButton(
                                  onPressed: () => copyText(context, formatForCopy([votd])),
                                  child: const Text('Copy'),
                                ),
                              ]),
                            ],
                          ),
                        ),
                    ],
                  ),
                  if (recent.isNotEmpty) ...[
                    const SizedBox(height: 28),
                    Text('Recent searches', style: t.titleSmall),
                    const SizedBox(height: 8),
                    Wrap(spacing: 8, runSpacing: 8, children: [
                      for (final r in recent)
                        InputChip(
                          avatar: Icon(r.mode == 'phrase' ? Icons.format_quote : Icons.search, size: 16),
                          label: Text(r.query),
                          onPressed: () => r.mode == 'phrase' ? app.nav.ask(r.query, mode: SearchMode.phrase) : app.nav.ask(r.query),
                        ),
                    ]),
                  ],
                  const SizedBox(height: 28),
                  _Card(
                    width: double.infinity,
                    icon: Icons.explore_outlined,
                    title: 'New to the scriptures?',
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('A short, neutral guide to what is here, how to ask questions, and how to read.'),
                        const SizedBox(height: 12),
                        OutlinedButton(
                          onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => GuideScreen(app: app))),
                          child: const Text('Start here'),
                        ),
                      ],
                    ),
                  ),
                  if (showKeyboardHints(context)) ...[
                    const SizedBox(height: 16),
                    Text('Tip: press Ctrl+K anywhere to jump to a verse or ask a question.', style: t.bodySmall),
                  ],
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

class _Card extends StatelessWidget {
  const _Card({required this.width, required this.icon, required this.title, required this.child});
  final double width;
  final IconData icon;
  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: BoxConstraints(maxWidth: width, minWidth: width == double.infinity ? 0 : 280),
      child: Card(
        margin: EdgeInsets.zero,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                Icon(icon, size: 18),
                const SizedBox(width: 8),
                Expanded(child: Text(title, maxLines: 1, overflow: TextOverflow.ellipsis, style: Theme.of(context).textTheme.labelLarge)),
              ]),
              const SizedBox(height: 12),
              child,
            ],
          ),
        ),
      ),
    );
  }
}

class _Notice extends StatelessWidget {
  const _Notice({required this.icon, required this.text, this.action, this.onAction});
  final IconData icon;
  final String text;
  final String? action;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.secondaryContainer.withValues(alpha: 0.5),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(children: [
        Icon(icon, size: 20),
        const SizedBox(width: 12),
        Expanded(child: Text(text)),
        if (action != null) TextButton(onPressed: onAction, child: Text(action!)),
      ]),
    );
  }
}
