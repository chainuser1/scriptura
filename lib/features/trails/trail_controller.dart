import 'package:flutter/foundation.dart';

import '../../app_controller.dart';
import '../../data/trails/trail_models.dart';
import '../../services/engine/search_models.dart';
import 'trail_catalog.dart';
import 'trail_reasons.dart';

enum TrailPhase { loading, ready, empty, engineDown }

/// One open trail: the queue, the feedback log and the state the screen shows. The engine holds no state; every batch
/// is requested with the full event log, so reopening a trail always reproduces it.
class TrailController extends ChangeNotifier {
  TrailController({required this.app, required Trail trail, TrailCatalog? catalog})
      : _trail = trail,
        _catalog = catalog;

  final AppController app;
  Trail _trail;
  TrailCatalog? _catalog;

  TrailPhase phase = TrailPhase.loading;
  int? current;
  final List<int> history = [];
  List<String> leans = const [];
  List<double> familyWeights = List.filled(23, 0.0);
  String? reasonHint;
  String? problem;
  TrailHitParts? currentParts;

  final List<int> _queue = [];
  final Map<int, TrailHitParts> _parts = {};
  List<TrailEvent> _events = [];
  Future<void> _chain = Future.value();
  var _disposed = false;

  Trail get trail => _trail;
  TrailCatalog get catalog => _catalog!;

  @override
  void notifyListeners() {
    if (!_disposed) super.notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }

  // ---- lifecycle -----------------------------------------------------------------------------------------------------
  Future<void> start() async {
    _catalog ??= await TrailCatalog.shared;
    _events = app.user.trailEvents(_trail.id);
    history
      ..clear()
      ..addAll(_distinct([for (final e in _events) if (e.action == TrailAction.shown) e.verseId]));
    if (!app.search.available) {
      phase = TrailPhase.engineDown;
      problem = app.search.unavailableReason;
      notifyListeners();
      return;
    }
    await _guard(() async {
      final last = _events.isEmpty ? null : _events.last;
      if (last != null && last.action == TrailAction.shown && _renderable(last.verseId)) {
        current = last.verseId;
        currentParts = _parts[last.verseId];
        await _refill();
        phase = TrailPhase.ready;
        notifyListeners();
      } else {
        await _advance();
      }
    });
  }

  Future<void> retry() => start();

  // ---- feedback ------------------------------------------------------------------------------------------------------
  /// Feedback is applied strictly in the order it was given, so rapid taps never interleave.
  Future<void> feedback(TrailAction action) {
    _chain = _chain.then((_) => _apply(action));
    return _chain;
  }

  Future<void> _apply(TrailAction action) async {
    final v = current;
    if (v == null || _disposed) return;
    _record(v, action);
    reasonHint = switch (action) {
      TrailAction.like => 'Close to ${_reference(v)}, which you liked',
      TrailAction.dislike => 'Different from ${_reference(v)}, which you disliked',
      _ => null,
    };
    _queue.clear();
    await _guard(_advance);
  }

  // ---- tuning --------------------------------------------------------------------------------------------------------
  Future<void> tune({List<String>? moods, double? focus, double? moodStrength, String? volume}) {
    _chain = _chain.then((_) async {
      app.user.updateTrail(_trail.id, moods: moods, focus: focus, moodStrength: moodStrength, volume: volume);
      _trail = app.user.trail(_trail.id)!;
      _queue.clear();
      await _guard(() async {
        await _refill();
        notifyListeners();
      });
    });
    return _chain;
  }

  Future<void> addSeed(TrailSeed seed) {
    _chain = _chain.then((_) async {
      app.user.addTrailSeed(_trail.id, seed);
      _queue.clear();
      await _guard(() async {
        await _refill();
        notifyListeners();
      });
    });
    return _chain;
  }

  void rename(String name) {
    final n = name.trim();
    if (n.isEmpty) return;
    app.user.updateTrail(_trail.id, name: n);
    _trail = app.user.trail(_trail.id)!;
    notifyListeners();
  }

  // ---- explanation ---------------------------------------------------------------------------------------------------
  Future<List<Reason>> why() async {
    final v = current;
    if (v == null) return const [];
    final anchor = _anchor();
    ExplainResult? ex;
    if (anchor != null && app.search.available) {
      try {
        final genes = <String>[for (final m in _trail.moods) for (final g in catalog.moodGenes(m)) g['id'] as String];
        ex = ExplainResult.fromResponse(await app.search.search(SearchRequest.raw('explain', {'a': anchor, 'b': v, 'mood_genes': genes})));
      } on SearchFailure {
        ex = null;
      }
    }
    return buildReasons(
      catalog: catalog,
      explain: ex,
      parts: _parts[v] ?? const TrailHitParts(),
      sharedQuestions: _sharedQuestions(anchor, v),
      moodLabels: [for (final m in _trail.moods) catalog.mood(m)?.label ?? m],
    );
  }

  /// The verse this card is explained against: your latest like, else the seed verse, else the previous card.
  int? _anchor() {
    for (final e in _events.reversed) {
      if (e.action == TrailAction.like) return e.verseId;
    }
    if (_trail.seed.verseId != null) return _trail.seed.verseId;
    final i = history.length - 2;
    return i >= 0 ? history[i] : null;
  }

  List<String> _sharedQuestions(int? a, int b) {
    final store = app.answers;
    if (store == null || a == null) return const [];
    final ids = store.forVerse(a, language: app.language).map((q) => q.id).toSet();
    return [for (final q in store.forVerse(b, language: app.language)) if (ids.contains(q.id)) q.text];
  }

  // ---- internals -----------------------------------------------------------------------------------------------------
  Map<String, dynamic> _request({int k = 10}) {
    final seeds = app.user.trailSeeds(_trail.id);
    return {
      'op': 'trail_next',
      'k': k,
      'step': history.length,
      'seed': _trail.seed.toEngine(),
      'extra_seeds': [for (final s in seeds) s.toEngine()],
      'events': [for (final e in _events) {'verse_id': e.verseId, 'action': e.action.name}],
      'recent': history.length <= 5 ? List<int>.of(history) : history.sublist(history.length - 5),
      'moods': [for (final m in _trail.moods) catalog.moodGenes(m)],
      'mood_strength': _trail.moodStrength,
      'focus': _trail.focus,
      'filter': _filter(),
      'language': app.language,
    };
  }

  List<List<int>>? _filter() {
    final v = _trail.volume;
    if (v == 'all') return null;
    final vols = app.repository?.volumes() ?? const [];
    List<int> range(String key) {
      final e = vols.where((x) => x.key == key).firstOrNull;
      return e == null ? const [] : [e.firstVerseId, e.lastVerseId];
    }

    final keys = v == 'bible' ? ['ot', 'nt'] : [v];
    final out = [for (final k in keys) range(k)].where((r) => r.length == 2).toList();
    return out.isEmpty ? null : out;
  }

  Future<void> _refill() async {
    final r = await app.search.search(SearchRequest.raw('trail_next', _request()));
    final b = TrailBatch.fromResponse(r);
    familyWeights = b.familyWeights;
    leans = b.leans;
    _queue
      ..clear()
      ..addAll(b.hits.map((h) => h.verseId));
    for (final h in b.hits) {
      _parts[h.verseId] = h.parts;
    }
  }

  Future<void> _advance() async {
    while (true) {
      if (_queue.isEmpty) {
        await _refill();
        if (_queue.isEmpty) {
          current = null;
          phase = TrailPhase.empty;
          notifyListeners();
          return;
        }
      }
      final v = _queue.removeAt(0);
      if (history.contains(v)) continue; // a card is never shown twice, whatever the engine returns
      _record(v, TrailAction.shown);
      if (!_renderable(v)) continue;
      current = v;
      currentParts = _parts[v];
      phase = TrailPhase.ready;
      notifyListeners();
      return;
    }
  }

  Future<void> _guard(Future<void> Function() body) async {
    try {
      problem = null;
      await body();
    } on SearchFailure catch (e) {
      problem = e.message;
      phase = current == null ? TrailPhase.engineDown : phase; // the card stays when there is one
      notifyListeners();
    }
  }

  void _record(int verse, TrailAction action) {
    app.user.addTrailEvent(_trail.id, verse, action);
    _events.add(TrailEvent(verse, action, DateTime.now()));
    if (action == TrailAction.shown && !history.contains(verse)) history.add(verse);
  }

  bool _renderable(int verse) {
    try {
      app.repository!.getPassage(verse, language: app.language);
      return true;
    } on Object {
      return false;
    }
  }

  String _reference(int verse) {
    try {
      return app.repository!.getPassage(verse, language: app.language).reference;
    } on Object {
      return 'that verse';
    }
  }

  static List<int> _distinct(Iterable<int> xs) {
    final seen = <int>{};
    return [for (final x in xs) if (seen.add(x)) x];
  }
}
