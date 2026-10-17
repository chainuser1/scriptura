
import 'package:flutter/material.dart';

import '../../app/contact.dart';
import '../../app/keyboard_hints.dart';
import '../../app/search_styles.dart';
import '../../app/version.dart';
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
