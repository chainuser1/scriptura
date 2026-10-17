import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../app_controller.dart';
import '../features/home/home_screen.dart';
import '../features/read/read_screen.dart';
import '../features/search/search_screen.dart';
import '../features/settings/settings_screen.dart';
import '../features/study/study_screen.dart';
import '../features/trails/return_bar.dart';
import '../services/engine/search_models.dart';
import 'brand.dart';
import 'desktop.dart';
import 'nav_state.dart';
import 'theme.dart';

const _destinations = <(Dest, IconData, IconData, String)>[
  (Dest.home, Icons.home_outlined, Icons.home, 'Home'),
  (Dest.read, Icons.menu_book_outlined, Icons.menu_book, 'Read'),
  (Dest.search, Icons.search, Icons.search, 'Search'),
  (Dest.study, Icons.collections_bookmark_outlined, Icons.collections_bookmark, 'Study'),
  (Dest.settings, Icons.settings_outlined, Icons.settings, 'Settings'),
];

/// Sidebar and content at 900 px and wider; bottom bar below that. Keyboard: Ctrl+K command bar, Ctrl+1..5 sections.
class AppShell extends StatefulWidget {
  const AppShell({super.key, required this.app});
  final AppController app;

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  final _visited = <Dest>{Dest.home};

  AppController get app => widget.app;

  Widget _page(Dest d) {
    // Edge-to-edge on Android: keep every page below the status bar. The reader is the exception because it paints
    // its own reading colour behind the bar.
    Widget clear(Widget page) => SafeArea(bottom: false, child: page);
    switch (d) {
      case Dest.home:
        return clear(HomeScreen(app: app));
      case Dest.read:
        return ReadScreen(app: app);
      case Dest.search:
        return clear(SearchScreen(app: app));
      case Dest.study:
        return clear(StudyScreen(app: app));
      case Dest.settings:
        return clear(SettingsScreen(app: app));
    }
  }

  // Ctrl+K is heard app-wide, not only while focus is inside the shell (a click on plain text drops focus).
  bool _barOpen = false;

  @override
  void initState() {
    super.initState();
    HardwareKeyboard.instance.addHandler(_onKey);
    Desktop.onQuickSearch(_commandBar);
    Desktop.configure(background: app.user.pref('background') != '0');
  }

  @override
  void dispose() {
    HardwareKeyboard.instance.removeHandler(_onKey);
    super.dispose();
  }

  bool _onKey(KeyEvent e) {
    final k = HardwareKeyboard.instance;
    // Ctrl+K, or Ctrl+Alt+Space when the system shortcut is not ours (Windows delivers that one through [Desktop]).
    final hit = e.logicalKey == LogicalKeyboardKey.keyK || (e.logicalKey == LogicalKeyboardKey.space && k.isAltPressed);
    if (e is! KeyDownEvent || !hit || !k.isControlPressed) return false;
    if (!_barOpen) _commandBar();
    return true;
  }

  Future<void> _commandBar() async {
    if (_barOpen) return;
    _barOpen = true;
    final String? text;
    try {
      text = await showDialog<String>(context: context, builder: (_) => const _CommandBar());
    } finally {
      _barOpen = false;
    }
    if (text == null || text.trim().isEmpty || !mounted) return;
    await runCommand(app, text.trim());
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: Listenable.merge([app, app.nav]),
      builder: (context, _) {
        final dest = app.nav.dest;
        _visited.add(dest);
        final index = _destinations.indexWhere((d) => d.$1 == dest);
        final wide = MediaQuery.sizeOf(context).width >= kWideBreakpoint;
        final body = IndexedStack(
          index: index,
          children: [for (final d in _destinations) _visited.contains(d.$1) ? _page(d.$1) : const SizedBox.shrink()],
        );
        // The return bar sits above the bottom navigation on narrow and at the foot of the content on wide.
        final content = Column(children: [Expanded(child: body), ReturnBar(app: app)]);
        final shortcuts = <ShortcutActivator, VoidCallback>{
          for (var i = 0; i < _destinations.length; i++)
            SingleActivator(LogicalKeyboardKey(LogicalKeyboardKey.digit1.keyId + i), control: true): () => app.nav.go(_destinations[i].$1),
        };
        return CallbackShortcuts(
          bindings: shortcuts,
          child: Focus(
            autofocus: true,
            child: Scaffold(
              body: wide
                  ? Row(children: [
                      NavigationRail(
                        selectedIndex: index,
                        labelType: NavigationRailLabelType.all,
                        onDestinationSelected: (i) => app.nav.go(_destinations[i].$1),
                        leading: Padding(
                          padding: const EdgeInsets.only(top: 12, bottom: 8),
                          child: Column(mainAxisSize: MainAxisSize.min, children: [
                            ScripturesMark(size: 40, onDark: Theme.of(context).brightness == Brightness.dark),
                            const SizedBox(height: 16),
                            IconButton.filledTonal(
                              tooltip: 'Go to a verse or ask a question (Ctrl+K)',
                              onPressed: _commandBar,
                              icon: const Icon(Icons.bolt),
                            ),
                          ]),
                        ),
                        trailing: Expanded(
                          child: Align(alignment: Alignment.bottomCenter, child: Padding(padding: const EdgeInsets.only(bottom: 16), child: _EngineDot(app: app))),
                        ),
                        destinations: [
                          for (final d in _destinations)
                            NavigationRailDestination(icon: Icon(d.$2), selectedIcon: Icon(d.$3), label: Text(d.$4)),
                        ],
                      ),
                      const VerticalDivider(),
                      Expanded(child: content),
                    ])
                  : content,
              bottomNavigationBar: wide
                  ? null
                  : NavigationBar(
                      selectedIndex: index,
                      onDestinationSelected: (i) => app.nav.go(_destinations[i].$1),
                      destinations: [
                        for (final d in _destinations) NavigationDestination(icon: Icon(d.$2), selectedIcon: Icon(d.$3), label: d.$4),
                      ],
                    ),
            ),
          ),
        );
      },
    );
  }
}

/// A reference opens the passage; anything else becomes a question. The engine understands references in every served
/// language; without it, only book names from the catalog are recognised.
Future<void> runCommand(AppController app, String text) async {
  final repo = app.repository;
  if (repo == null) return;
  if (app.engineState == EngineState.ready) {
    try {
      final r = await app.search.search(SearchRequest.reference(text, language: app.language));
      final ref = r.reference;
      if (ref != null && ref.status == 'ok' && ref.firstVerseId != null) {
        final c = repo.catalog.chapterOfVerse(ref.firstVerseId!);
        if (c != null) {
          final verse = ref.kind == 'verse' || ref.kind == 'range' || ref.kind == 'range_x' ? ref.firstVerseId! - c.firstVerseId + 1 : null;
          app.nav.openChapter(c.bookId, c.chapter, verseNumber: verse);
          return;
        }
      }
    } on Object {
      // fall through to a normal question
    }
  } else {
    final book = repo.catalog.resolve(text, language: app.language);
    if (book != null) {
      app.nav.openChapter(book.id, 1);
      return;
    }
  }
  app.nav.ask(text);
}

class _CommandBar extends StatefulWidget {
  const _CommandBar();
  @override
  State<_CommandBar> createState() => _CommandBarState();
}

class _CommandBarState extends State<_CommandBar> {
  final _c = TextEditingController();

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      alignment: Alignment.topCenter,
      insetPadding: const EdgeInsets.only(top: 80, left: 24, right: 24),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 640),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              TextField(
                controller: _c,
                autofocus: true,
                textInputAction: TextInputAction.go,
                onSubmitted: (v) => Navigator.pop(context, v),
                decoration: const InputDecoration(
                  prefixIcon: Icon(Icons.bolt),
                  hintText: 'Go to a verse (John 3:16) or ask a question',
                ),
              ),
              const SizedBox(height: 8),
              Text('Enter to go · Esc to close', style: Theme.of(context).textTheme.bodySmall),
            ],
          ),
        ),
      ),
    );
  }
}

class _EngineDot extends StatelessWidget {
  const _EngineDot({required this.app});
  final AppController app;

  @override
  Widget build(BuildContext context) {
    final (color, label) = switch (app.engineState) {
      EngineState.ready => (Colors.green, 'Search is ready'),
      EngineState.preparing => (Colors.amber, 'Search is starting'),
      EngineState.unavailable => (Theme.of(context).colorScheme.error, app.engineProblem ?? 'Search is unavailable'),
    };
    return Tooltip(
      message: label,
      child: Semantics(
        label: label,
        child: Container(width: 10, height: 10, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
      ),
    );
  }
}
