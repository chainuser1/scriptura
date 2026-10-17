import 'dart:async';

import 'package:flutter/material.dart';

import '../../app/guide_content.dart';
import '../../app/looks.dart';
import '../../app/nav_state.dart';
import '../../app/theme.dart';
import '../../app/verse_tools.dart';
import '../../app_controller.dart';
import '../../services/engine/answer_focus.dart';
import '../../data/content/content_repository.dart';
import '../../data/trails/trail_models.dart';
import '../../services/engine/search_models.dart';
import '../../services/engine/search_service.dart';
import '../trails/start_trail.dart';

/// Meaning and exact-phrase search with an honest account of what was understood, results beside a live preview of
/// the passage in context, and similar verses.
class SearchScreen extends StatefulWidget {
  const SearchScreen({super.key, required this.app});
  final AppController app;

  @override
  State<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends State<SearchScreen> {
  final _text = TextEditingController();
  SearchMode _mode = SearchMode.meaning;
  int? _scopeVolume;
  int? _activeRequest;
  bool _busy = false;
  String? _error;
  bool _cancelledNote = false;
  SearchResponse? _response;
  String _title = '';
  String _lastQuery = '';
  List<Passage> _passages = const [];
  Passage? _selected;
  final _resultsScroll = ScrollController();

  AppController get app => widget.app;
  ContentRepository get repo => app.repository!;
  SearchService get _service => app.search;

  @override
  void initState() {
    super.initState();
    app.nav.addListener(_onNav);
    WidgetsBinding.instance.addPostFrameCallback((_) => _onNav());
  }

  @override
  void dispose() {
    app.nav.removeListener(_onNav);
    if (_activeRequest != null) _service.cancel(_activeRequest!);
    _text.dispose();
    _resultsScroll.dispose();
    super.dispose();
  }

  void _onNav() {
    if (!mounted || app.nav.dest != Dest.search) return;
    final p = app.nav.takePending();
    if (p == null) return;
    if (p.similarTo != null) {
      _text.text = '';
      _runSimilar(p.similarTo!, p.query);
    } else {
      setState(() {
        _mode = p.mode;
        _text.text = p.query;
      });
      _submit();
    }
  }

  List<VerseRange>? get _filter {
    if (_scopeVolume == null) return null;
    final v = repo.volumes(language: app.language).firstWhere((v) => v.id == _scopeVolume);
    return [VerseRange(v.firstVerseId, v.lastVerseId)];
  }

  Future<void> _run(SearchRequest Function() build, {required String title, String? remember, String mode = 'meaning', String? focus}) async {
    if (_activeRequest != null) _service.cancel(_activeRequest!);
    final id = _service.nextRequestId();
    setState(() {
      _activeRequest = id;
      _busy = true;
      _error = null;
      _cancelledNote = false;
      _title = title;
    });
    try {
      final r = await _service.search(build(), requestId: id);
      if (!mounted || _activeRequest != id) return;
      if (remember != null) app.user.rememberSearch(remember, mode);
      var passages = _resolve(r);
      if (focus != null && r.mode != 'reference') passages = await _focus(focus, passages, id);
      if (!mounted || _activeRequest != id) return;
      setState(() {
        _response = r;
        _passages = passages;
        _selected = passages.isEmpty ? null : passages.first;
        _busy = false;
      });
      // a new search is read from its first result, not from where the last list happened to be scrolled
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_resultsScroll.hasClients) _resultsScroll.jumpTo(0);
      });
    } on SearchFailure catch (e) {
      if (!mounted || _activeRequest != id) return;
      setState(() {
        _busy = false;
        if (e.cancelled) {
          _cancelledNote = true;
        } else {
          _error = _explain(e);
          _response = null;
          _passages = const [];
          _selected = null;
        }
      });
    }
  }

  /// Answer focus: the top results reordered by how well each answers [query]. Today's order whenever focus is not
  /// installed, fails, or takes longer than twice the budget; the request shares the search's id, so a newer search
  /// cancels it.
  Future<List<Passage>> _focus(String query, List<Passage> passages, int id) async {
    final choice = app.focusChoice;
    if (!_service.hasFocus || choice == null || choice.k == 0 || passages.length < 2) return passages;
    final top = passages.take(choice.k).toList();
    try {
      final r = await _service
          .search(SearchRequest.raw('focus', {'query': query, 'texts': [for (final p in top) p.text]}), requestId: id)
          .timeout(Duration(milliseconds: (2 * kFocusBudgetMs).round()));
      final scores = [for (final s in r.raw['scores'] as List) (s as num).toDouble()];
      if (scores.length != top.length) return passages;
      app.recordFocusTime((r.raw['ms'] as num).toDouble(), device: r.raw['device'] as String?);
      return focusOrder(passages, scores);
    } on TimeoutException {
      _service.cancel(id);
      return passages;
    } on Object {
      return passages; // focus_unavailable, a driver error, a cancel: today's order
    }
  }

  String _explain(SearchFailure e) {
    switch (e.code) {
      case 'invalid_input':
        return e.message;
      case 'unsupported_language':
        return 'Exact phrase search is not available in this language.';
      case 'missing_pack':
        return e.message;
      case 'unknown_verse':
        return 'That verse is not in the search index.';
      default:
        return 'Search failed (${e.code}): ${e.message}';
    }
  }

  List<Passage> _resolve(SearchResponse r) {
    final out = <Passage>[];
    for (final h in r.hits) {
      try {
        out.add(repo.getPassage(h.verseId, language: app.language));
      } on Object {
        // a verse missing from the repository is skipped, never shown blank
      }
    }
    return out;
  }

  void _submit([String? _]) {
    final q = _text.text.trim();
    if (q.isEmpty) return;
    _lastQuery = q;
    if (_mode == SearchMode.phrase) {
      _run(() => SearchRequest.phrase(q, language: app.language, filter: _filter),
          title: 'Exact phrase', remember: q, mode: 'phrase');
    } else {
      _run(() => SearchRequest.search(q, language: app.language, filter: _filter, profile: app.searchProfile), title: 'Passages for “$q”', remember: q, focus: q);
    }
  }

  void _runSimilar(int verseId, String label) {
    _lastQuery = label;
    _run(() => SearchRequest.similar(verseId, filter: _filter), title: label);
  }

  void _pickPerson(String entityId) {
    _run(() => SearchRequest.search(_lastQuery, language: app.language, filter: _filter, person: entityId, profile: app.searchProfile), title: 'Passages for “$_lastQuery”', focus: _lastQuery);
  }

  void _open(Passage p) => app.nav.openChapter(p.bookId, p.chapter, verseNumber: p.verse);

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: Listenable.merge([app, app.user]),
      builder: (context, _) {
        final wide = MediaQuery.sizeOf(context).width >= kSplitBreakpoint;
        final results = _body(context);
        return Column(
          children: [
            _queryBar(context),
            const Divider(),
            Expanded(
              child: wide && _selected != null && _response != null && _response!.mode != 'reference'
                  ? Row(children: [
                      Expanded(flex: 5, child: results),
                      const VerticalDivider(),
                      Expanded(flex: 4, child: _Preview(app: app, passage: _selected!, onOpen: _open)),
                    ])
                  : results,
            ),
          ],
        );
      },
    );
  }

  Widget _queryBar(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          TextField(
            controller: _text,
            textInputAction: TextInputAction.search,
            onSubmitted: _submit,
            decoration: InputDecoration(
              hintText: _mode == SearchMode.meaning ? 'Ask a question, name a topic, or type a reference' : 'Type the exact words',
              prefixIcon: const Icon(Icons.search),
              suffixIcon: _busy
                  ? IconButton(tooltip: 'Cancel search', icon: const Icon(Icons.close), onPressed: () => _service.cancel(_activeRequest!))
                  : IconButton(tooltip: 'Search', icon: const Icon(Icons.arrow_forward), onPressed: _submit),
            ),
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 12,
            runSpacing: 8,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              SegmentedButton<SearchMode>(
                showSelectedIcon: false,
                segments: const [
                  ButtonSegment(value: SearchMode.meaning, label: Text('Meaning'), icon: Icon(Icons.psychology_alt_outlined)),
                  ButtonSegment(value: SearchMode.phrase, label: Text('Exact phrase'), icon: Icon(Icons.format_quote)),
                ],
                selected: {_mode},
                onSelectionChanged: (s) => setState(() => _mode = s.first),
              ),
              SizedBox(
                width: 260,
                child: DropdownButton<int?>(
                  isExpanded: true,
                  value: _scopeVolume,
                  items: [
                    const DropdownMenuItem<int?>(value: null, child: Text('Across the canon')),
                    for (final v in repo.volumes(language: app.language))
                      DropdownMenuItem<int?>(value: v.id, child: Text(v.name, overflow: TextOverflow.ellipsis)),
                  ],
                  onChanged: (v) => setState(() => _scopeVolume = v),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _body(BuildContext context) {
    if (app.engineState == EngineState.preparing) {
      return const _Message(icon: Icons.hourglass_top, text: 'Preparing search…');
    }
    if (app.engineState == EngineState.unavailable) {
      return _Message(
        icon: Icons.search_off,
        text: '${app.engineProblem ?? 'Search is not available.'}\n\nReading still works.',
        action: 'Open Settings',
        onAction: () => app.nav.go(Dest.settings),
      );
    }
    if (_error != null) return _Message(icon: Icons.error_outline, text: _error!);
    if (_busy && _response == null) return const Center(child: CircularProgressIndicator());
    final r = _response;
    if (r == null) return _emptyState(context);
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 900),
        child: ListView(
          key: const ValueKey('search-results'),
          controller: _resultsScroll,
          padding: const EdgeInsets.only(bottom: 32),
          children: [
            if (_busy) const LinearProgressIndicator(),
            if (_cancelledNote) const Padding(padding: EdgeInsets.all(16), child: Text('Search cancelled. Showing the previous results.')),
            ..._interpretation(context, r),
            if (r.mode == 'reference') ..._referenceCard(context, r.reference!) else ..._results(context, r),
          ],
        ),
      ),
    );
  }

  Widget _emptyState(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final recent = app.user.recentSearches(limit: 8);
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 760),
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (_cancelledNote) const Padding(padding: EdgeInsets.only(bottom: 12), child: Text('Search cancelled.')),
              Text('What would you like to find?', style: t.titleLarge),
              const SizedBox(height: 8),
              const Text('Ask in your own words, search for exact words, or type a reference such as John 3:16.'),
              const SizedBox(height: 20),
              Text('Try asking', style: t.titleSmall),
              const SizedBox(height: 8),
              Wrap(spacing: 8, runSpacing: 8, children: [
                for (final q in starterQuestions)
                  ActionChip(
                    label: Text(q),
                    onPressed: () {
                      _text.text = q;
                      setState(() => _mode = SearchMode.meaning);
                      _submit();
                    },
                  ),
              ]),
              if (recent.isNotEmpty) ...[
                const SizedBox(height: 24),
                Row(children: [
                  Text('Recent', style: t.titleSmall),
                  const Spacer(),
                  TextButton(onPressed: app.user.clearSearchHistory, child: const Text('Clear')),
                ]),
                Wrap(spacing: 8, runSpacing: 8, children: [
                  for (final r in recent)
                    InputChip(
                      avatar: Icon(r.mode == 'phrase' ? Icons.format_quote : Icons.search, size: 16),
                      label: Text(r.query),
                      onPressed: () {
                        _text.text = r.query;
                        setState(() => _mode = r.mode == 'phrase' ? SearchMode.phrase : SearchMode.meaning);
                        _submit();
                      },
                    ),
                ]),
              ],
              const SizedBox(height: 24),
              Text('Good to know', style: t.titleSmall),
              const SizedBox(height: 6),
              const Text('• Meaning finds passages that speak to your question, even in different words.'),
              const Text('• Exact phrase finds verses containing those words in that order, and counts them.'),
              const Text('• Use the scope menu to search only one volume.'),
            ],
          ),
        ),
      ),
    );
  }

  Iterable<Widget> _interpretation(BuildContext context, SearchResponse r) sync* {
    final p = r.person;
    if (p != null) {
      yield Padding(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              p.status == 'ambiguous'
                  ? 'Several people or places share this name. Which one?'
                  : p.status == 'generic'
                      ? 'Showing the best passages about ${p.people.first.name}.'
                      : p.people.first.entityId.startsWith('place:')
                          ? 'Showing passages about the place you named.'
                          : p.people.first.entityId.startsWith('group:')
                              ? 'Showing passages about the people you named.'
                              : 'Showing passages about the person you named.',
              style: Theme.of(context).textTheme.labelLarge,
            ),
            const SizedBox(height: 6),
            Wrap(spacing: 8, runSpacing: 4, children: [
              for (final c in p.people)
                ChoiceChip(
                  selected: c.selected && p.status != 'ambiguous',
                  label: Text(
                    [c.name, if (c.qualifier.isNotEmpty) c.qualifier, if (c.entityId.startsWith('place:')) 'place' else if (c.entityId.startsWith('group:')) 'people'].join(' · '),
                    overflow: TextOverflow.ellipsis,
                  ),
                  onSelected: (_) => _pickPerson(c.entityId),
                ),
            ]),
          ],
        ),
      );
    }
    if (r.profileFellBack) {
      yield Padding(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 0),
        child: Text('Using the ${r.profile} search profile because the optional word-level index is not installed.',
            style: Theme.of(context).textTheme.bodySmall),
      );
    }
  }

  Passage? _safe(int verseId) {
    try {
      return repo.getPassage(verseId, language: app.language);
    } on Object {
      return null;
    }
  }

  Iterable<Widget> _referenceCard(BuildContext context, ReferenceResult ref) sync* {
    switch (ref.status) {
      case 'ok':
        final first = _safe(ref.firstVerseId!);
        final label = first == null
            ? '${ref.book}'
            : ref.firstVerseId == ref.lastVerseId
                ? first.reference
                : '${first.reference} – ${_safe(ref.lastVerseId!)?.reference ?? ''}';
        yield Card(
          margin: const EdgeInsets.all(20),
          child: ListTile(
            leading: const Icon(Icons.bookmark_outlined),
            title: Text('Open $label'),
            subtitle: first == null ? null : Text(first.text, maxLines: 3, overflow: TextOverflow.ellipsis),
            onTap: first == null ? null : () => _open(first),
          ),
        );
      case 'ambiguous':
        yield const Padding(padding: EdgeInsets.fromLTRB(20, 16, 20, 4), child: Text('That name matches more than one book:'));
        for (final c in ref.candidates) {
          yield ListTile(leading: const Icon(Icons.book_outlined), title: Text(c.book), onTap: () => app.nav.openChapter(c.bookId, 1));
        }
      case 'out_of_range':
        yield Padding(padding: const EdgeInsets.all(20), child: Text(ref.reason ?? 'That reference does not exist.'));
    }
  }

  Iterable<Widget> _results(BuildContext context, SearchResponse r) sync* {
    final t = Theme.of(context);
    if (_passages.isEmpty) {
      yield Padding(
        padding: const EdgeInsets.all(24),
        child: Text(r.mode == 'phrase'
            ? 'No verse contains that exact phrase. Try fewer words, or search by meaning.'
            : 'No passages found. Try different words.'),
      );
      return;
    }
    final heading = r.mode == 'phrase'
        ? '${r.total} verse${r.total == 1 ? '' : 's'} contain “$_lastQuery”${r.truncated ? ' · showing the first ${_passages.length}' : ''}'
        : r.mode == 'similar'
            ? _title
            : _title;
    yield Padding(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 4),
      child: Semantics(header: true, child: Text(heading, style: t.textTheme.titleSmall)),
    );
    if (r.mode != 'phrase' && r.mode != 'similar') {
      // The trail keeps to what answered the question: the question itself plus the top three results.
      yield Padding(
        padding: const EdgeInsets.fromLTRB(12, 0, 20, 4),
        child: Align(
          alignment: Alignment.centerLeft,
          child: TextButton.icon(
            icon: const Icon(Icons.alt_route),
            label: const Text('Start a trail from this question'),
            onPressed: () => startTrail(context, app,
                seed: TrailSeed.question(_lastQuery),
                name: _lastQuery,
                extraSeeds: [for (final p in _passages.take(3)) TrailSeed.verse(p.verseId)]),
          ),
        ),
      );
    }
    final phrase = r.mode == 'phrase' ? _lastQuery : null;
    final wide = MediaQuery.sizeOf(context).width >= kSplitBreakpoint;
    for (final p in _passages) {
      final selected = _selected?.verseId == p.verseId;
      yield ListTile(
        key: ValueKey('hit-${p.verseId}'),
        selected: selected && wide,
        selectedTileColor: t.colorScheme.primaryContainer.withValues(alpha: 0.45),
        title: Text(p.reference, style: const TextStyle(fontWeight: FontWeight.w600)),
        subtitle: _snippet(context, p.text, phrase),
        onTap: () => wide ? setState(() => _selected = p) : _open(p),
        trailing: PopupMenuButton<String>(
          tooltip: 'More',
          onSelected: (v) {
            switch (v) {
              case 'open':
                _open(p);
              case 'similar':
                _runSimilar(p.verseId, 'Verses similar to ${p.reference}');
              case 'trail':
                startTrail(context, app, seed: TrailSeed.verse(p.verseId), name: p.reference);
              case 'copy':
                copyText(context, formatForCopy([p]), message: 'Copied with reference');
              case 'bookmark':
                app.user.toggleBookmark(p.verseId);
            }
          },
          itemBuilder: (_) => const [
            PopupMenuItem(value: 'open', child: Text('Read in context')),
            PopupMenuItem(value: 'similar', child: Text('Similar verses')),
            PopupMenuItem(value: 'trail', child: Text('Start a trail from this verse')),
            PopupMenuItem(value: 'copy', child: Text('Copy with reference')),
            PopupMenuItem(value: 'bookmark', child: Text('Bookmark')),
          ],
        ),
      );
    }
  }

  Widget _snippet(BuildContext context, String text, String? phrase) {
    final style = Theme.of(context).textTheme.bodyMedium!;
    if (phrase == null || phrase.isEmpty) return Text(text, maxLines: 4, overflow: TextOverflow.ellipsis);
    final i = text.toLowerCase().indexOf(phrase.toLowerCase());
    if (i < 0) return Text(text, maxLines: 4, overflow: TextOverflow.ellipsis);
    return Text.rich(
      TextSpan(style: style, children: [
        TextSpan(text: text.substring(0, i)),
        TextSpan(
          text: text.substring(i, i + phrase.length),
          style: TextStyle(fontWeight: FontWeight.bold, backgroundColor: highlightPalette[0]),
        ),
        TextSpan(text: text.substring(i + phrase.length)),
      ]),
      maxLines: 4,
      overflow: TextOverflow.ellipsis,
    );
  }
}

/// The selected result inside its chapter, so the answer can be judged in context without leaving the results.
class _Preview extends StatelessWidget {
  const _Preview({required this.app, required this.passage, required this.onOpen});
  final AppController app;
  final Passage passage;
  final void Function(Passage) onOpen;

  @override
  Widget build(BuildContext context) {
    final repo = app.repository!;
    final user = app.user;
    final prefs = ReadingPrefs.of(user);
    final theme = prefs.theme;
    final chapter = repo.getChapter(passage.bookId, passage.chapter, language: app.language);
    final around = chapter.where((p) => (p.verse - passage.verse).abs() <= 6).toList();
    final style = prefs.style(color: theme.text, extraScale: 0.9);
    return Container(
      color: theme.background,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
            child: Row(children: [
              Expanded(child: Text(passage.reference, style: style.copyWith(fontSize: 22, fontWeight: FontWeight.w600))),
              IconButton(
                tooltip: user.isBookmarked(passage.verseId) ? 'Remove bookmark' : 'Bookmark',
                icon: Icon(user.isBookmarked(passage.verseId) ? Icons.bookmark : Icons.bookmark_border, color: theme.text),
                onPressed: () => user.toggleBookmark(passage.verseId),
              ),
              IconButton(
                tooltip: 'Copy with reference',
                icon: Icon(Icons.copy, color: theme.text),
                onPressed: () => copyText(context, formatForCopy([passage]), message: 'Copied with reference'),
              ),
            ]),
          ),
          Expanded(
            child: SelectionArea(
              child: ListView(
                key: ValueKey('preview-${passage.verseId}'), // a new passage starts at its top
                padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
                children: [
                  for (final p in around)
                    Container(
                      margin: const EdgeInsets.symmetric(vertical: 2),
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: p.verse == passage.verse ? highlightPalette[0] : null,
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Text.rich(
                        TextSpan(children: [
                          TextSpan(text: '${p.verse}  ', style: style.copyWith(fontSize: style.fontSize! * 0.62, fontWeight: FontWeight.bold)),
                          TextSpan(text: p.text),
                        ]),
                        style: style,
                      ),
                    ),
                ],
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(12),
            child: Wrap(spacing: 8, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
              FilledButton.tonal(onPressed: () => onOpen(passage), child: const Text('Read the chapter')),
              TextButton(
                onPressed: () => app.nav.askSimilar(passage.verseId, 'Verses similar to ${passage.reference}'),
                child: Text('Similar verses', style: TextStyle(color: theme.text)),
              ),
            ]),
          ),
        ],
      ),
    );
  }
}

class _Message extends StatelessWidget {
  const _Message({required this.icon, required this.text, this.action, this.onAction});
  final IconData icon;
  final String text;
  final String? action;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Icon(icon, size: 40),
            const SizedBox(height: 12),
            Text(text, textAlign: TextAlign.center),
            if (action != null) ...[const SizedBox(height: 12), FilledButton.tonal(onPressed: onAction, child: Text(action!))],
          ]),
        ),
      );
}
