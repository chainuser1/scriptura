import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';

import '../../app/looks.dart';
import '../../app/nav_state.dart';
import '../../app_controller.dart';
import '../../data/content/content_repository.dart';
import '../../data/trails/trail_models.dart';
import 'trail_card.dart';
import 'trail_catalog.dart';
import 'trail_controller.dart';
import 'tune_sheet.dart';
import 'why_sheet.dart';

class TrailScreen extends StatefulWidget {
  const TrailScreen({super.key, required this.app, required this.trail, this.catalog});
  final AppController app;
  final Trail trail;
  final TrailCatalog? catalog;

  @override
  State<TrailScreen> createState() => _TrailScreenState();
}

class _TrailScreenState extends State<TrailScreen> {
  late final TrailController c = TrailController(app: widget.app, trail: widget.trail, catalog: widget.catalog);
  int? _announced;

  AppController get app => widget.app;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => app.nav.setTrailOpen(true));
    c.addListener(_announce);
    c.start();
  }

  @override
  void dispose() {
    c.removeListener(_announce);
    c.dispose();
    WidgetsBinding.instance.addPostFrameCallback((_) => app.nav.setTrailOpen(false));
    super.dispose();
  }

  void _announce() {
    final v = c.current;
    if (v == null || v == _announced || !mounted) return;
    _announced = v;
    try {
      final p = app.repository!.getPassage(v, language: app.language);
      SemanticsService.sendAnnouncement(View.of(context), '${p.reference}. ${c.reasonHint ?? ''}', Directionality.of(context));
    } on Object {
      // announcing is a courtesy
    }
  }

  void _feedback(TrailAction a) {
    if (c.phase != TrailPhase.ready) return;
    if (a == TrailAction.like || a == TrailAction.dislike) HapticFeedback.selectionClick();
    c.feedback(a);
  }

  Future<void> _why() => showWhy(context, c);

  Future<void> _tune() => showTune(context, c, onAddVariety: _addVariety);

  Future<void> _addVariety() async {
    final text = TextEditingController();
    final q = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Add variety'),
        content: TextField(controller: text, autofocus: true, decoration: const InputDecoration(labelText: 'A question to blend in', hintText: 'How do I find peace?')),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, text.text.trim()), child: const Text('Add')),
        ],
      ),
    );
    text.dispose();
    if (q != null && q.isNotEmpty) await c.addSeed(TrailSeed.question(q));
  }

  Future<void> _rename() async {
    final text = TextEditingController(text: c.trail.name);
    final name = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Rename this trail'),
        content: TextField(controller: text, autofocus: true),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, text.text), child: const Text('Save')),
        ],
      ),
    );
    text.dispose();
    if (name != null) c.rename(name);
  }

  void _delete() {
    final snap = app.user.deleteTrail(c.trail.id);
    final messenger = ScaffoldMessenger.of(context);
    Navigator.of(context).pop();
    messenger.showSnackBar(SnackBar(
      content: const Text('Trail deleted'),
      action: SnackBarAction(label: 'Undo', onPressed: () => app.user.restoreTrail(snap)),
    ));
  }

  @override
  Widget build(BuildContext context) {
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.keyL): () => _feedback(TrailAction.like),
        const SingleActivator(LogicalKeyboardKey.keyD): () => _feedback(TrailAction.dislike),
        const SingleActivator(LogicalKeyboardKey.keyS): () => _feedback(TrailAction.skip),
        const SingleActivator(LogicalKeyboardKey.arrowRight): () => _feedback(TrailAction.skip),
        const SingleActivator(LogicalKeyboardKey.keyW): _why,
        const SingleActivator(LogicalKeyboardKey.keyT): _tune,
        const SingleActivator(LogicalKeyboardKey.escape): () => Navigator.of(context).maybePop(),
      },
      child: Focus(
        autofocus: true,
        child: ListenableBuilder(
          listenable: Listenable.merge([c, app.user]),
          builder: (context, _) => Scaffold(
            appBar: AppBar(
              title: Text(c.trail.name, overflow: TextOverflow.ellipsis),
              actions: [
                // phones: icon only, so the trail name keeps its room
                if (MediaQuery.sizeOf(context).width < 600)
                  IconButton(onPressed: _tune, tooltip: 'Tune', icon: const Icon(Icons.tune))
                else
                  TextButton.icon(onPressed: _tune, icon: const Icon(Icons.tune), label: const Text('Tune')),
                PopupMenuButton<String>(
                  tooltip: 'More',
                  onSelected: (v) {
                    switch (v) {
                      case 'rename':
                        _rename();
                      case 'variety':
                        _addVariety();
                      case 'delete':
                        _delete();
                    }
                  },
                  itemBuilder: (_) => const [
                    PopupMenuItem(value: 'rename', child: Text('Rename')),
                    PopupMenuItem(value: 'variety', child: Text('Add variety')),
                    PopupMenuItem(value: 'delete', child: Text('Delete trail')),
                  ],
                ),
              ],
            ),
            body: _body(context),
          ),
        ),
      ),
    );
  }

  Widget _body(BuildContext context) {
    final t = Theme.of(context).textTheme;
    switch (c.phase) {
      case TrailPhase.loading:
        return const Center(child: SizedBox(width: 360, child: Card(child: SizedBox(height: 180))));
      case TrailPhase.engineDown:
        return _Message(
          icon: Icons.search_off,
          text: c.problem ?? 'Search data is not installed.',
          actions: [
            FilledButton(
              onPressed: () {
                app.nav.go(Dest.settings);
                Navigator.of(context).pop();
              },
              child: const Text('Open Settings'),
            ),
            TextButton(onPressed: c.retry, child: const Text('Try again')),
          ],
        );
      case TrailPhase.empty:
        return _Message(
          icon: Icons.flag_outlined,
          text: 'This trail has played everything close to it.',
          actions: [
            FilledButton(onPressed: _addVariety, child: const Text('Add variety')),
            TextButton(onPressed: _tune, child: const Text('Tune')),
          ],
        );
      case TrailPhase.ready:
        break;
    }
    final catalog = c.catalog;
    final passage = _passage(c.current!);
    final user = app.user;
    final prefs = ReadingPrefs.of(user);
    final reduce = MediaQuery.disableAnimationsOf(context);
    final leans = c.leans.isEmpty ? null : 'This trail leans toward ${c.leans.map((l) => catalog.familyLabel(l).toLowerCase()).join(' and ')}';
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 760),
        child: Column(children: [
          if (c.problem != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
              child: Material(
                color: Theme.of(context).colorScheme.errorContainer,
                borderRadius: BorderRadius.circular(8),
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(12, 4, 4, 4),
                  child: Row(children: [
                    Expanded(child: Text(c.problem!, style: TextStyle(color: Theme.of(context).colorScheme.onErrorContainer))),
                    TextButton(onPressed: c.retry, child: const Text('Try again')),
                  ]),
                ),
              ),
            ),
          if (c.trail.moods.isNotEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Wrap(spacing: 8, children: [
                  for (final id in c.trail.moods)
                    InputChip(
                      label: Text(catalog.mood(id)?.label ?? id),
                      onDeleted: () => c.tune(moods: [...c.trail.moods]..remove(id)),
                      deleteButtonTooltipMessage: 'Remove this mood',
                    ),
                ]),
              ),
            ),
          if (leans != null) Padding(padding: const EdgeInsets.fromLTRB(20, 8, 20, 0), child: Align(alignment: Alignment.centerLeft, child: Text(leans, style: t.bodySmall))),
          Expanded(
            child: LayoutBuilder(
              builder: (context, box) => SingleChildScrollView(
                padding: const EdgeInsets.all(16),
                child: ConstrainedBox(
                  constraints: BoxConstraints(minHeight: box.maxHeight - 32),
                  child: Center(
                    child: Column(mainAxisSize: MainAxisSize.min, children: [
                      AnimatedSwitcher(
                        duration: reduce ? Duration.zero : const Duration(milliseconds: 180),
                        transitionBuilder: (child, anim) => FadeTransition(
                          opacity: anim,
                          child: SlideTransition(position: Tween(begin: const Offset(0.06, 0), end: Offset.zero).animate(anim), child: child),
                        ),
                        child: KeyedSubtree(
                          key: ValueKey(c.current),
                          child: TrailCard(
                            passage: passage,
                            prefs: prefs,
                            bookmarked: user.isBookmarked(passage.verseId),
                            onBookmark: () => user.toggleBookmark(passage.verseId),
                            hint: c.reasonHint,
                          ),
                        ),
                      ),
                    ]),
                  ),
                ),
              ),
            ),
          ),
          // The actions stay put below the card: a long verse scrolls, the buttons never leave the screen.
          // Two buttons only. "Less like this" is the strong negative (it also hides near neighbours); it is a quiet text
          // action, worded for scripture rather than as a thumbs-down.
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              Wrap(alignment: WrapAlignment.center, spacing: 12, runSpacing: 8, children: [
                _Action(label: 'Skip', tooltip: 'Skip this verse', icon: Icons.skip_next, onPressed: () => _feedback(TrailAction.skip)),
                _Action(label: 'Like', tooltip: 'Like: show more like this', icon: Icons.thumb_up_outlined, filled: true, onPressed: () => _feedback(TrailAction.like)),
              ]),
              const SizedBox(height: 4),
              Wrap(alignment: WrapAlignment.center, spacing: 4, children: [
                TextButton(onPressed: () => _feedback(TrailAction.dislike), child: const Text('Less like this')),
                TextButton.icon(onPressed: _why, icon: const Icon(Icons.expand_more), label: const Text('Why this verse')),
              ]),
            ]),
          ),
          // keep the earlier-verses row clear of the phone's navigation bar (the trail is its own route, no shell inset)
          SafeArea(top: false, child: _History(controller: c, app: app)),
        ]),
      ),
    );
  }

  Passage _passage(int id) => app.repository!.getPassage(id, language: app.language);
}

class _Action extends StatelessWidget {
  const _Action({required this.label, required this.tooltip, required this.icon, required this.onPressed, this.filled = false});
  final String label, tooltip;
  final IconData icon;
  final VoidCallback onPressed;
  final bool filled;

  @override
  Widget build(BuildContext context) {
    const style = ButtonStyle(minimumSize: WidgetStatePropertyAll(Size(128, 56)));
    return Tooltip(
      message: tooltip,
      child: filled
          ? FilledButton.icon(onPressed: onPressed, icon: Icon(icon), label: Text(label), style: style)
          : OutlinedButton.icon(onPressed: onPressed, icon: Icon(icon), label: Text(label), style: style),
    );
  }
}

class _History extends StatelessWidget {
  const _History({required this.controller, required this.app});
  final TrailController controller;
  final AppController app;

  @override
  Widget build(BuildContext context) {
    final earlier = controller.history.where((v) => v != controller.current).toList().reversed.take(12).toList();
    if (earlier.isEmpty) return const SizedBox(height: 8);
    return SizedBox(
      height: 52,
      child: ListView(scrollDirection: Axis.horizontal, padding: const EdgeInsets.symmetric(horizontal: 12), children: [
        for (final v in earlier)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 8),
            child: ActionChip(
              label: Text(() {
                try {
                  return app.repository!.getPassage(v, language: app.language).shortened;
                } on Object {
                  return '$v';
                }
              }()),
              onPressed: () {
                final p = app.repository!.getPassage(v, language: app.language);
                Navigator.of(context).pop();
                app.nav.openChapter(p.bookId, p.chapter, verseNumber: p.verse);
              },
            ),
          ),
      ]),
    );
  }
}

class _Message extends StatelessWidget {
  const _Message({required this.icon, required this.text, required this.actions});
  final IconData icon;
  final String text;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) => Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(32),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Icon(icon, size: 40),
            const SizedBox(height: 12),
            Text(text, textAlign: TextAlign.center, style: Theme.of(context).textTheme.bodyLarge),
            const SizedBox(height: 16),
            Wrap(alignment: WrapAlignment.center, spacing: 8, children: actions),
          ]),
        ),
      );
}
