
import 'package:flutter/material.dart';

import '../../app/contact.dart';
import '../../app/desktop.dart';
import '../../app/keyboard_hints.dart';
import '../../app/search_styles.dart';
import '../../app/version.dart';
import '../../services/engine/answer_focus.dart';
import '../../services/update_check.dart';
import '../../app_controller.dart';
import '../../services/engine/benchmark.dart';
import '../data/setup_progress.dart';
import 'reading_controls.dart';
import '../about/about_screen.dart';
import '../guide/guide_screen.dart';

String _label(String language) => language[0].toUpperCase() + language.substring(1);

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key, required this.app});
  final AppController app;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  String? _working;
  String? _speed;

  AppController get app => widget.app;

  Future<void> _measure() async {
    setState(() {
      _working = 'Measuring search speed…';
    });
    try {
      final r = await runBenchmark(app.search, rounds: 1);
      final w = r['warm_total_ms'] as Map;
      if (mounted) setState(() => _speed = 'Median ${(w['median'] as double).round()} ms, slowest ${(w['max'] as double).round()} ms.');
    } on Object catch (e) {
      if (mounted) setState(() => _speed = 'Could not measure: $e');
    } finally {
      if (mounted) setState(() => _working = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: Listenable.merge([app, app.user]),
      builder: (context, _) {
        final repo = app.repository!;
        final user = app.user;
        final t = Theme.of(context).textTheme;
        final parallel = user.pref('parallel');
        final langs = repo.servedLanguages;
        final colbert = app.canInstall ? app.colbertPacks.active() : null;
        Widget header(String s) => Padding(padding: const EdgeInsets.fromLTRB(0, 28, 0, 8), child: Semantics(header: true, child: Text(s.toUpperCase(), style: t.labelLarge?.copyWith(fontWeight: FontWeight.w700, letterSpacing: 1.2, color: Theme.of(context).colorScheme.primary))));
        return Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 760),
            child: ListView(
              padding: const EdgeInsets.all(24),
              children: [
                Text('Settings', style: t.headlineSmall),
                header('Look and feel'),
                LookGallery(user: user, wrapWhenWide: true),
                Theme(
                  data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
                  child: ExpansionTile(
                    tilePadding: EdgeInsets.zero,
                    title: const Text('Fine-tune the look'),
                    subtitle: const Text('Page colour, typeface, size, spacing, line width, verse numbers, layout'),
                    childrenPadding: const EdgeInsets.only(bottom: 8),
                    expandedCrossAxisAlignment: CrossAxisAlignment.start,
                    children: [ReadingControls(user: user)],
                  ),
                ),
                ReadingPreview(user: user),
                const SizedBox(height: 20),
                Text('App theme', style: t.titleSmall),
                const SizedBox(height: 8),
                AppThemeGallery(user: user),
                header('Reading'),
                ListTile(
                  title: const Text('Language'),
                  subtitle: const Text('Used for the scriptures, book names and results'),
                  trailing: DropdownButton<String>(
                    value: app.language,
                    items: [for (final l in langs) DropdownMenuItem(value: l, child: Text(_label(l)))],
                    onChanged: (l) => l == null ? null : app.setLanguage(l),
                  ),
                ),
                if (langs.length > 1)
                  ListTile(
                    title: const Text('Second language beside the text'),
                    subtitle: const Text('Parallel reading for comparison and study'),
                    trailing: DropdownButton<String?>(
                      value: parallel != null && langs.contains(parallel) && parallel != app.language ? parallel : null,
                      items: [
                        const DropdownMenuItem<String?>(value: null, child: Text('None')),
                        for (final l in langs.where((l) => l != app.language)) DropdownMenuItem<String?>(value: l, child: Text(_label(l))),
                      ],
                      onChanged: (l) => user.setPref('parallel', l ?? ''),
                    ),
                  ),
                header('Search data'),
                if (_working != null) ...[Text(_working!), const SizedBox(height: 6), const LinearProgressIndicator(), const SizedBox(height: 12)],
                ListTile(
                  leading: Icon(app.engineState == EngineState.ready ? Icons.check_circle_outline : Icons.info_outline),
                  title: const Text('Search'),
                  subtitle: Text(switch (app.engineState) {
                    EngineState.ready => app.search.hasColbertPack ? 'Ready — full precision' : 'Ready — without the optional word-level index',
                    EngineState.preparing => 'Starting…',
                    EngineState.unavailable => app.setupStatus ?? app.engineProblem ?? 'Unavailable',
                  }),
                  trailing: app.engineState == EngineState.ready ? TextButton(onPressed: _working != null ? null : _measure, child: const Text('Measure speed')) : null,
                ),
                if (_speed != null) Padding(padding: const EdgeInsets.only(left: 16, bottom: 8), child: Text(_speed!)),
                if (colbert == null && app.engineState == EngineState.ready)
                  const ListTile(leading: Icon(Icons.lightbulb_outline), title: Text('Optional word-level index'), subtitle: Text('Installing it makes results for subtle wording slightly more precise. It is large (about 3 GB).')),
                if (app.canInstall) SetupProgress(app: app),
                if (Desktop.supported)
                  ValueListenableBuilder(
                    valueListenable: Desktop.hotkey,
                    builder: (context, ours, _) => SwitchListTile(
                      secondary: const Icon(Icons.keyboard_command_key),
                      title: const Text('Quick search from anywhere'),
                      subtitle: Text(ours == false
                          ? 'Another program is using Ctrl+Alt+Space, so it works only inside Scriptura. Closing the window still keeps Scriptura in the tray.'
                          : 'Ctrl+Alt+Space opens the quick search from any program. Closing the window keeps Scriptura in the tray; choose Quit from its tray icon to end it.'),
                      value: user.pref('background') != '0',
                      onChanged: (on) {
                        user.setPref('background', on ? '1' : '0');
                        Desktop.configure(background: on);
                      },
                    ),
                  ),
                header('Advanced'),
                Theme(
                  data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
                  child: ExpansionTile(
                    tilePadding: const EdgeInsets.symmetric(horizontal: 16),
                    leading: const Icon(Icons.tune),
                    title: const Text('Search style'),
                    subtitle: Text(
                      searchStyles.firstWhere((s) => s.id == (user.pref('search_profile') ?? kDefaultSearchStyle), orElse: () => searchStyles.first).name,
                    ),
                    children: [
                      Padding(
                        padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                        child: Text(
                          'How the app weighs meaning, exact words and the verse fingerprint. Compass suits almost every question; '
                          'try another if results feel off for the kind of question you ask.',
                          style: t.bodySmall,
                        ),
                      ),
                      RadioGroup<String>(
                        groupValue: user.pref('search_profile') ?? kDefaultSearchStyle,
                        onChanged: (v) => v == null ? null : app.setSearchProfile(v),
                        child: Column(children: [
                          for (final s in searchStyles)
                            RadioListTile<String>(
                              value: s.id,
                              title: Text(s.id == kDefaultSearchStyle ? '${s.name} (recommended)' : s.name),
                              subtitle: Text(
                                s.needsIndex && !app.search.hasColbertPack ? '${s.summary} Uses Lantern until the word-level index is installed.' : s.summary,
                              ),
                            ),
                        ]),
                      ),
                    ],
                  ),
                ),
                _AnswerFocusTile(app: app),
                if (showKeyboardHints(context)) ...[
                  header('Keyboard'),
                  const _Shortcuts(),
                ],
                header('About'),
                ListTile(
                  leading: const Icon(Icons.auto_stories_outlined),
                  title: const Text('Our story'),
                  subtitle: const Text('Why Scriptura exists'),
                  onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const AboutScreen())),
                ),
                ListTile(
                  leading: const Icon(Icons.language),
                  title: const Text('Website'),
                  subtitle: const Text(kWebsiteLabel),
                  onTap: () => openOrCopy(context, Uri.parse(kWebsite), kWebsite),
                ),
                ListTile(
                  leading: const Icon(Icons.mail_outline),
                  title: const Text('Contact us'),
                  subtitle: const Text(kContactEmail),
                  onTap: () => openOrCopy(context, contactUri(), kContactEmail),
                ),
                ListTile(
                  leading: const Icon(Icons.bug_report_outlined),
                  title: const Text('Report a problem'),
                  subtitle: const Text('Opens an email to us with your app version and device'),
                  onTap: () => openOrCopy(context, reportProblemUri(), kContactEmail),
                ),
                ListTile(
                  leading: const Icon(Icons.explore_outlined),
                  title: const Text('Start here'),
                  subtitle: const Text('A short orientation to the library and how to use it'),
                  onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => GuideScreen(app: app))),
                ),
                ListTile(
                  leading: const Icon(Icons.info_outline),
                  title: const Text('Sources and licences'),
                  subtitle: const Text('Version $kAppVersion'),
                  onTap: () => _about(context),
                ),
                if (kReleasesApi.isNotEmpty)
                  ListTile(
                    leading: const Icon(Icons.system_update_alt),
                    title: const Text('Check for updates'),
                    subtitle: const Text('Looks at the project\'s latest release. Nothing about you is sent.'),
                    onTap: () => _checkUpdates(context),
                  ),
                if (app.userProblem != null)
                  ListTile(
                    leading: Icon(Icons.warning_amber, color: Theme.of(context).colorScheme.error),
                    title: const Text('Your saved data could not be opened'),
                    subtitle: Text('${app.userProblem}. It was left untouched; changes this session are not saved.'),
                  ),
                const SizedBox(height: 24),
                Text('Your bookmarks, highlights and notes are stored only on this computer.', style: t.bodySmall),
              ],
            ),
          ),
        );
      },
    );
  }

  Future<void> _checkUpdates(BuildContext context) async {
    String title;
    String body;
    String? url;
    try {
      final u = await checkForUpdate(api: kReleasesApi, current: kAppVersion);
      if (u.isNewer) {
        title = 'Version ${u.latest} is available';
        body = 'You have $kAppVersion.';
        url = u.downloadForThisPlatform ?? u.pageUrl;
      } else {
        title = 'You are up to date';
        body = 'Version $kAppVersion is the latest.';
      }
    } on Object catch (e) {
      title = 'Could not check';
      body = 'The release page could not be read ($e). Try again later.';
    }
    if (!context.mounted) return;
    final link = url;
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(title),
        content: Text(body),
        actions: [
          if (link != null)
            TextButton(
              onPressed: () async {
                await openOrCopy(context, Uri.parse(link), link);
                if (ctx.mounted) Navigator.pop(ctx);
              },
              child: const Text('Open download'),
            ),
          FilledButton(onPressed: () => Navigator.pop(ctx), child: const Text('Close')),
        ],
      ),
    );
  }

  void _about(BuildContext context) {
    final repo = app.repository!;
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Sources and licences'),
        content: SizedBox(
          width: 520,
          child: SingleChildScrollView(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
              const Text(
                'The Bible text (Genesis to Revelation) is in the public domain: the King James Version in English, and public-domain '
                'translations in the other languages. The licence and copyright of the Book of Mormon, Doctrine and Covenants and '
                'Pearl of Great Price belong to The Church of Jesus Christ of Latter-day Saints (© Intellectual Reserve, Inc.); their '
                'use is subject to the Church\'s terms and is not covered by this app\'s licence. Each verse records its source, and '
                'a language is offered only where the library holds a complete text.',
              ),
              const SizedBox(height: 12),
              Text('Languages in this library: ${repo.servedLanguages.map(_label).join(', ')}.'),
              const SizedBox(height: 12),
              const Text(
                'The app\'s code is released under the MIT licence, © 2026 Scriptura Labs. That licence covers the code and the project\'s own '
                'machine-generated data, not the scripture text.',
              ),
              const SizedBox(height: 12),
              const Text(
                'Search by meaning uses an on-device language model and a per-verse profile; it runs entirely offline. '
                'Recognising people by name uses a machine-generated index and can be wrong, which is why the app shows what it '
                'understood and lets you choose.',
              ),
              const SizedBox(height: 12),
              const Text('Descriptions of the volumes are written to state what each is and who holds it, without argument.'),
              const SizedBox(height: 12),
              const Text('Scripture text is set in Source Serif 4 © Adobe by default, and optionally in Literata © The Literata Project Authors or Atkinson Hyperlegible © Braille Institute of America, all used under the SIL Open Font License 1.1.'),
            ]),
          ),
        ),
        actions: [FilledButton(onPressed: () => Navigator.pop(ctx), child: const Text('Close'))],
      ),
    );
  }
}

class _Shortcuts extends StatelessWidget {
  const _Shortcuts();

  @override
  Widget build(BuildContext context) {
    const rows = [
      ('Ctrl+K', 'Go to a verse or ask a question'),
      ('Ctrl+1 … 5', 'Home, Read, Search, Study, Settings'),
      ('← →', 'Previous / next chapter while reading'),
      ('Ctrl + / Ctrl −', 'Larger / smaller text'),
      ('Click or right-click a verse', 'Copy, bookmark, highlight, note, similar verses'),
    ];
    return Column(children: [
      for (final r in rows)
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 4, horizontal: 16),
          child: Row(children: [
            SizedBox(width: 210, child: Text(r.$1, style: const TextStyle(fontWeight: FontWeight.w600))),
            Expanded(child: Text(r.$2)),
          ]),
        ),
    ]);
  }
}

/// Answer focus (Settings › Advanced): what this device uses, the Automatic / On / Off choice, the download when it is
/// offered, and Measure again.
class _AnswerFocusTile extends StatelessWidget {
  const _AnswerFocusTile({required this.app});
  final AppController app;

  String _status() {
    final c = app.focusChoice;
    if (app.focusMode == FocusMode.off) return 'Off: search works as usual.';
    if (app.search.hasFocus && c != null && c.variant != FocusVariant.none) {
      final gpu = (app.focusDevice ?? (c.variant == FocusVariant.fp16 ? 'gpu' : 'cpu')) == 'gpu';
      return 'Using the ${gpu ? 'graphics chip' : 'processor'}, on the top ${c.k} results.';
    }
    if (c == null) return 'Not measured yet.';
    if (c.variant == FocusVariant.none) return 'This device is too slow for it; search works as usual. Choose On to use it anyway.';
    final size = switch ((c.model, c.variant)) {
      (FocusModel.apollos, FocusVariant.fp16) => 'about 2.5 GB',
      (FocusModel.apollos, FocusVariant.int8) => 'about 2 GB',
      (FocusModel.ezra, FocusVariant.fp16) => 'about 1 GB',
      (FocusModel.ezra, FocusVariant.int8) => 'about 400 MB',
      _ => 'a download',
    };
    return 'This device will use the ${c.variant == FocusVariant.fp16 ? 'graphics chip' : 'processor'}. Not downloaded yet ($size, best on Wi-Fi).';
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.center_focus_strong_outlined),
          const SizedBox(width: 16),
          Expanded(child: Text('Answer focus', style: t.titleMedium)),
        ]),
        Padding(
          padding: const EdgeInsets.only(left: 40, top: 4),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('Puts the passages that answer your question first. Chosen for this device automatically.', style: t.bodySmall),
            const SizedBox(height: 4),
            Text(_status()),
            const SizedBox(height: 12),
            _ModelPicker(app: app),
            const SizedBox(height: 8),
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: SegmentedButton<FocusMode>(
                segments: const [
                  ButtonSegment(value: FocusMode.automatic, label: Text('Automatic')),
                  ButtonSegment(value: FocusMode.on, label: Text('On')),
                  ButtonSegment(value: FocusMode.off, label: Text('Off')),
                ],
                selected: {app.focusMode},
                onSelectionChanged: (s) => app.setFocusMode(s.first),
              ),
            ),
            Wrap(spacing: 8, children: [
              if (app.canInstall && !app.focusInstalled && app.focusMode != FocusMode.off && (app.focusChoice?.variant ?? FocusVariant.none) != FocusVariant.none)
                FilledButton(onPressed: app.setupBusy ? null : () => app.ensureData(includeFocus: true), child: const Text('Download')),
              if (app.offerAnswerFocus) TextButton(onPressed: app.declineAnswerFocus, child: const Text('Not now')),
              TextButton(onPressed: app.engineState == EngineState.ready ? app.remeasure : null, child: const Text('Measure again')),
            ]),
          ]),
        ),
      ]),
    );
  }
}

/// Which model Answer focus uses on this device: Ezra or Apollos. Picking Apollos always re-measures; if the trial
/// shows it does not fit this device, a dialog asks whether to try it anyway (it stays selectable, never greyed out).
class _ModelPicker extends StatefulWidget {
  const _ModelPicker({required this.app});
  final AppController app;

  @override
  State<_ModelPicker> createState() => _ModelPickerState();
}

class _ModelPickerState extends State<_ModelPicker> {
  AppController get app => widget.app;
  bool _checking = false;

  Future<void> _selectApollos() async {
    setState(() => _checking = true);
    app.setFocusModelPreference(FocusModel.apollos);
    await app.remeasure();
    setState(() => _checking = false);
    // Anything other than Apollos itself -- Ezra's own fallback, or FocusVariant.none when even Ezra's budget
    // fails under Automatic -- means Apollos genuinely did not fit this device's trial.
    final doesNotFit = app.focusChoice?.model != FocusModel.apollos;
    if (doesNotFit && !app.apollosOverrideAccepted && mounted) await _warn();
  }

  Future<void> _warn() async {
    final proceed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('This device may not be fast enough for Apollos'),
        content: const Text(
          'Ezra works better here. You can still try Apollos -- it is experimental and may take much longer to '
          'search, or affect your experience. Download it anyway?',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Use Ezra instead')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Try Apollos anyway')),
        ],
      ),
    );
    if (proceed == true) {
      app.acceptApollosOverride();
    } else {
      app.setFocusModelPreference(FocusModel.ezra);
      await app.remeasure();
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: SegmentedButton<FocusModel>(
          segments: const [
            ButtonSegment(value: FocusModel.ezra, label: Text('Ezra')),
            ButtonSegment(value: FocusModel.apollos, label: Text('Apollos')),
            ButtonSegment(value: FocusModel.priscilla, label: Text('Priscilla')),
          ],
          selected: {app.focusModelPreference},
          // Same gate as Measure again: a pick the engine cannot trial would leave the old model running.
          onSelectionChanged: app.engineState == EngineState.ready && !_checking
              ? (s) {
                  if (s.first == FocusModel.apollos) {
                    _selectApollos();
                  } else {
                    // Ezra and Priscilla both just switch and remeasure -- neither has a warning dialog.
                    app.setFocusModelPreference(s.first);
                    app.remeasure();
                  }
                }
              : null,
        ),
      ),
      const SizedBox(height: 4),
      Text(
        switch (app.focusModelPreference) {
          FocusModel.ezra => 'Ezra: a steady, well-tested choice that works on every device.',
          FocusModel.apollos => 'Apollos: looks harder for the exact answer, but is slower and experimental -- a good fit if you '
              'don\'t mind waiting a bit longer for more refined results.',
          FocusModel.priscilla => 'Priscilla: a lighter model that\'s quick on most devices -- a good middle ground between '
              'Ezra\'s speed and Apollos\'s deeper search.',
        },
        style: t.bodySmall,
      ),
    ]);
  }
}
