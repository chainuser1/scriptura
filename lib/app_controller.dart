import 'dart:convert';
import 'dart:io';

import 'dart:isolate';

import 'package:flutter/foundation.dart';

import 'data/answers/answers_store.dart';
import 'data/content/catalog.dart';
import 'data/content/content_database.dart';
import 'data/content/content_repository.dart';
import 'data/user/user_store.dart';
import 'app/hosting.dart';
import 'app/nav_state.dart';
import 'services/artifacts/release_store.dart';
import 'services/engine/answer_focus.dart';
import 'services/engine/downloader.dart';
import 'services/engine/engine_bindings.dart';
import 'services/engine/engine_pack.dart';
import 'services/engine/search_models.dart';
import 'services/engine/search_service.dart';

enum EngineState { preparing, ready, unavailable }

/// First-run data setup (see [AppController.ensureData]).
enum SetupPhase { idle, checking, downloading, unpacking, paused, failed }

/// Owns what the app is currently running on: the content repository (text and catalog) and the search service
/// (native engine). Missing data is fetched automatically from the published address ([ensureData]).
class AppController extends ChangeNotifier {
  /// [devPacks]: a directory holding side-loaded `release/`, `engine-pack/` and `colbert-pack-v1/` folders (used for
  /// device benchmarks; production installs go through the Data screen).
  AppController({required Directory root, Map<String, String>? environment, this.devPacks})
      : _root = root,
        _env = environment ?? Platform.environment;

  /// For widget tests: fixed repository and service, no installation.
  AppController.fixed({ContentRepository? repository, SearchService? search, UserStore? user})
      : _root = null,
        _user = user,
        _env = const {},
        devPacks = null,
        _repository = repository,
        _search = search ?? UnavailableSearchService('Search is not available in this build'),
        _state = (search == null || !search.available) ? EngineState.unavailable : EngineState.ready,
        _engineProblem = search == null ? 'Search is not available in this build' : search.unavailableReason;

  final Directory? _root;
  final Directory? devPacks;
  String? devInstallError;
  final NavState nav = NavState();
  UserStore? _user;
  String? userProblem;
  final Map<String, String> _env;
  ContentRepository? _repository;
  ContentDatabase? _content;
  SearchService _search = UnavailableSearchService('Search is starting');
  EngineState _state = EngineState.preparing;
  String? _engineProblem;

  ContentRepository? get repository => _repository;

  /// Personal data (bookmarks, highlights, notes, preferences). Always usable: if the saved file cannot be opened it
  /// is left untouched and an in-memory store is used for the session, with [userProblem] explaining why.
  UserStore get user => _user ??= UserStore.memory();

  /// Language of the reading view and results; stored as a preference and limited to served languages.
  String get language {
    final saved = user.pref('language');
    final served = _repository?.servedLanguages ?? const ['english'];
    return saved != null && served.contains(saved) ? saved : 'english';
  }

  void setLanguage(String l) {
    user.setPref('language', l);
    notifyListeners();
  }
  SearchService get search => _search;
  EngineState get engineState => _state;
  String? get engineProblem => _engineProblem;
  bool get canInstall => _root != null;

  ReleaseStore get releases => ReleaseStore(Directory('${_root!.path}/scriptura'));
  PackStore get enginePacks => PackStore(Directory('${_root!.path}/scriptura'), PackKind.engine);
  PackStore get colbertPacks => PackStore(Directory('${_root!.path}/scriptura'), PackKind.colbert);
  PackStore get entityPacks => PackStore(Directory('${_root!.path}/scriptura'), PackKind.entities);
  PackStore get topicPacks => PackStore(Directory('${_root!.path}/scriptura'), PackKind.topics);
  PackStore get answerPacks => PackStore(Directory('${_root!.path}/scriptura'), PackKind.answers);
  PackStore get focusInt8Packs => PackStore(Directory('${_root!.path}/scriptura'), PackKind.focusInt8);
  PackStore get focusFp16Packs => PackStore(Directory('${_root!.path}/scriptura'), PackKind.focusFp16);

  /// Answer focus setting (Settings › Advanced): Automatic, On or Off.
  FocusMode get focusMode => FocusMode.parse(user.pref('answer_focus'));

  /// What the device trial chose (and later measurements adjusted); null until the trial has run.
  FocusChoice? get focusChoice => FocusChoice.fromJson(user.pref('answer_focus_choice'));

  String? get _focusKind => switch (focusChoice?.variant) {
        FocusVariant.int8 => 'answer-focus-int8',
        FocusVariant.fp16 => 'answer-focus-fp16',
        _ => null,
      };

  /// The installed pack for the current choice, unless Answer focus is off.
  InstalledPack? _focusPack() {
    if (_root == null || focusMode == FocusMode.off) return null;
    return switch (focusChoice?.variant) {
      FocusVariant.int8 => focusInt8Packs.active(),
      FocusVariant.fp16 => focusFp16Packs.active(),
      _ => null,
    };
  }

  bool get focusInstalled => _focusPack() != null;

  /// Offered once everything required is installed, the trial chose a model and the reader has not said "not now".
  bool get offerAnswerFocus =>
      _root != null &&
      _focusKind != null &&
      !focusInstalled &&
      focusMode != FocusMode.off &&
      user.pref('focus_declined') != '1' &&
      missingData.difference({'colbert'}).isEmpty &&
      _state == EngineState.ready;

  final _focusTimes = <double>[];

  /// Where Answer focus last ran ('gpu' or 'cpu'); null until the first focused search.
  String? focusDevice;

  /// A measured Answer focus time; after a few, Automatic adjusts how many results it reorders (or turns itself off).
  void recordFocusTime(double ms, {String? device}) {
    focusDevice = device ?? focusDevice;
    final c = focusChoice;
    if (c == null) return;
    if (c.variant == FocusVariant.fp16 && device == 'cpu') user.setPref('focus_gpu_failed', '1'); // the engine fell back
    _focusTimes.add(ms);
    final next = adapt(c, _focusTimes, focusMode);
    if (next != c) {
      user.setPref('answer_focus_choice', next.toJson());
      _focusTimes.clear();
    }
  }

  /// Automatic, On or Off. Off unloads the model; On also re-checks a device Automatic had found too slow.
  Future<void> setFocusMode(FocusMode m) async {
    user.setPref('answer_focus', m.name);
    notifyListeners();
    if (m != FocusMode.off && (focusChoice == null || focusChoice!.variant == FocusVariant.none)) await measureDevice();
    if (_root != null) await _startEngine();
  }

  void declineAnswerFocus() {
    user.setPref('focus_declined', '1');
    notifyListeners();
  }

  /// Times this device with the installed search model and decides Answer focus (see answer_focus.dart). Quiet on failure.
  /// A trial left pending (the app died during it, for example in a graphics driver) skips the graphics probe; a
  /// graphics chip that failed at run time is not offered again. An installed model is kept (see [keep]).
  /// Returns whether the chosen model changed.
  Future<bool> measureDevice() async {
    final before = focusChoice;
    final probeGpu = user.pref('focus_trial_pending') != '1' && user.pref('focus_gpu_failed') != '1';
    user.setPref('focus_trial_pending', '1');
    try {
      final r = await _search.search(SearchRequest.raw('device_trial', {if (!probeGpu) 'probe_gpu': false}));
      final fresh = choose(cpuMs: (r.raw['cpu_ms'] as num).toDouble(), gpu: probeGpu && r.raw['gpu'] == true, mode: focusMode);
      final installed = _root == null
          ? FocusVariant.none
          : focusInt8Packs.active() != null
              ? FocusVariant.int8
              : focusFp16Packs.active() != null
                  ? FocusVariant.fp16
                  : FocusVariant.none;
      final c = keep(before, fresh, installed: installed);
      user.setPref('answer_focus_choice', c.toJson());
      _focusTimes.clear();
      notifyListeners();
      return c.variant != before?.variant;
    } on Object {
      return false; // no choice yet; the trial runs again on the next start
    } finally {
      user.setPref('focus_trial_pending', '0');
    }
  }

  /// Settings › Measure again: a new trial, and the engine reopened when the chosen model changed.
  Future<void> remeasure() async {
    if (await measureDevice() && _root != null) await _startEngine();
  }

  AnswersStore? _answers;

  /// The reader's chosen search mix (Settings > Advanced), or null for the engine's default (Compass).
  String? get searchProfile {
    final p = user.pref('search_profile');
    return p == null || p.isEmpty || p == 'compass' ? null : p;
  }

  void setSearchProfile(String id) {
    user.setPref('search_profile', id);
    notifyListeners();
  }

  /// Study questions a passage speaks to; null until the answers pack is installed.
  AnswersStore? get answers => _answers;

  void _loadAnswers() {
    _answers?.dispose();
    _answers = null;
    final pack = _root == null ? null : answerPacks.active();
    if (pack != null) _answers = AnswersStore.tryOpen(pack.path('answers.db'));
  }

  /// Text and catalog first (fast), then the engine in the background.
  Future<void> load() async {
    final dev = devPacks;
    if (activeRelease == null && dev != null && File('${dev.path}/release/manifest.json').existsSync()) {
      try {
        await releases.installFromDirectory(Directory('${dev.path}/release'),
            include: {...requiredReleaseFiles, 'phrase-index.db'});
      } on Object catch (e) {
        devInstallError = '$e'; // surfaced as 'not installed'; also written to the device benchmark status
      }
    }
    _loadContent();
    _loadAnswers();
    notifyListeners();
    await _startEngine();
  }

  ActiveRelease? get activeRelease => _root == null ? null : releases.active();

  void _loadContent() {
    _repository = null;
    _content?.dispose();
    _content = null;
    if (_root != null) {
      _user?.dispose();
      _user = null;
    }
    final release = activeRelease;
    if (release == null) return;
    ContentDatabase? content;
    try {
      content = ContentDatabase.open(release.path('content.db'));
      _repository = ContentRepository(content, Catalog.load(release.path('catalog.db'), contract: content.contract));
      _content = content;
      final root = _root;
      if (root != null) {
        try {
          Directory('${root.path}/scriptura').createSync(recursive: true);
          _user = UserStore.open('${root.path}/scriptura/user.db', contract: content.contract);
          userProblem = null;
        } on UserDataException catch (e) {
          userProblem = e.message;
        } on Object catch (e) {
          userProblem = 'your saved data could not be opened: $e';
        }
      }
    } on ContentException {
      content?.dispose();
    }
  }

  InstalledPack? _packFromDirectory(String? dir) {
    if (dir == null) return null;
    final m = File('$dir/manifest.json');
    if (!m.existsSync()) return null;
    return InstalledPack(Directory(dir), jsonDecode(m.readAsStringSync()) as Map<String, dynamic>);
  }

  InstalledPack? _enginePack() =>
      _packFromDirectory(_env['SCRIPTURA_ENGINE_PACK']) ??
      _packFromDirectory(devPacks == null ? null : '${devPacks!.path}/engine-pack') ??
      (_root == null ? null : enginePacks.active());

  InstalledPack? _topicsPack() => _root == null ? null : topicPacks.active();

  InstalledPack? _entityPack() => _root == null ? null : entityPacks.active();

  InstalledPack? _colbertPack() =>
      _packFromDirectory(_env['SCRIPTURA_COLBERT_PACK']) ??
      _packFromDirectory(devPacks == null ? null : '${devPacks!.path}/colbert-pack-v1') ??
      (_root == null ? null : colbertPacks.active());

  Future<void> _engineOpen = Future.value();

  /// One engine (re)start at a time: two overlapping restarts would leave an engine and its model loaded.
  Future<void> _startEngine() => _engineOpen = _engineOpen.then((_) => _startEngineNow(), onError: (_) => _startEngineNow());

  Future<void> _startEngineNow() async {
    await _search.close();
    _state = EngineState.preparing;
    _engineProblem = null;
    notifyListeners();
    String? problem;
    SearchService? service;
    try {
      final lib = EnginePaths.findLibrary(env: _env);
      final engine = _enginePack();
      final colbert = _colbertPack();
      final release = activeRelease;
      if (lib == null) {
        problem = 'The search engine library (scripture_engine) was not found next to the app.';
      } else if (engine == null) {
        problem = 'The search data pack is not installed. Import it from Settings > Data.';
      } else if (release == null) {
        problem = 'Scripture content is not installed.';
      } else {
        final phrase = File(release.path('phrase-index.db'));
        final paths = EnginePaths(
          libraryPath: lib,
          engine: engine,
          colbert: colbert,
          phraseDb: phrase.existsSync() ? phrase.path : null,
          catalogDb: release.path('catalog.db'),
          entitiesDb: _entityPack()?.path('entities.db'),
          topicsDb: _topicsPack()?.path('topics.db'),
          focus: _focusPack(),
          focusGpu: focusChoice?.variant == FocusVariant.fp16 && user.pref('focus_gpu_failed') != '1',
        );
        service = await NativeSearchService.open(libraryPath: lib, config: paths.config());
      }
    } on SearchFailure catch (e) {
      problem = e.message;
    } catch (e) {
      problem = 'The search engine could not start: $e';
    }
    if (service != null) {
      _search = service;
      _state = EngineState.ready;
    } else {
      _search = UnavailableSearchService(problem ?? 'Search is unavailable');
      _state = EngineState.unavailable;
      _engineProblem = problem;
    }
    notifyListeners();
    // the trial runs after search is ready, never holding it up
    if (service != null && focusChoice == null && focusMode != FocusMode.off && _root != null) focusTrial = measureDevice();
  }

  /// The first-start device trial, while it runs.
  Future<bool>? focusTrial;

  Future<void> installRelease(Directory source) async {
    final manifest = jsonDecode(File('${source.path}/manifest.json').readAsStringSync()) as Map<String, dynamic>;
    final listed = (manifest['files'] as Map).keys.cast<String>().toSet();
    final include = {...requiredReleaseFiles, if (listed.contains('phrase-index.db')) 'phrase-index.db'};
    await releases.installFromDirectory(source, include: include);
    await load();
  }

  /// What a chosen folder offers: itself and its direct children are inspected for a content release, an engine pack
  /// and the optional ColBERT pack, so one folder (for example `generated-artifacts`) installs everything.
  static List<({String kind, Directory dir})> detectPacks(Directory folder) {
    final found = <({String kind, Directory dir})>[];
    void inspect(Directory d) {
      final f = File('${d.path}/manifest.json');
      if (!f.existsSync()) return;
      try {
        final m = jsonDecode(f.readAsStringSync()) as Map<String, dynamic>;
        final format = m['format'];
        if (format == 'engine-pack-v1') {
          found.add((kind: 'engine', dir: d));
        } else if (format == 'colbert-pack-v1') {
          found.add((kind: 'colbert', dir: d));
        } else if (m['release'] != null && (m['files'] as Map?)?.containsKey('content.db') == true) {
          found.add((kind: 'release', dir: d));
        }
      } on Object {
        // not one of ours
      }
    }

    inspect(folder);
    if (folder.existsSync()) {
      for (final e in folder.listSync(followLinks: true)) {
        if (e is Directory) inspect(e);
      }
    }
    return found;
  }

  /// Installs every pack found in [folder]; returns what was installed. Throws [PackException] when none is found.
  Future<List<String>> installFromFolder(Directory folder, {void Function(String what, double? fraction)? onProgress}) async {
    final packs = detectPacks(folder);
    if (packs.isEmpty) {
      throw PackException('nothing_found', 'No scripture content or search data was found in that folder.');
    }
    final done = <String>[];
    // content first (reading needs it), then search data, then the optional index
    for (final kind in const ['release', 'engine', 'colbert']) {
      for (final p in packs.where((p) => p.kind == kind)) {
        final label = switch (kind) { 'release' => 'scripture content', 'engine' => 'search data', _ => 'word-level index' };
        onProgress?.call(label, 0);
        void progress(int d, int t, String f) => onProgress?.call(label, t == 0 ? null : d / t);
        switch (kind) {
          case 'release':
            await installRelease(p.dir);
          case 'engine':
            await enginePacks.installFromDirectory(p.dir, onProgress: progress);
          default:
            await colbertPacks.installFromDirectory(p.dir, onProgress: progress);
        }
        done.add(label);
      }
    }
    await load();
    return done;
  }

  /// What a host at [base] offers (index.json), for the user to choose from.
  Future<RemoteIndex> checkHost(String base) async {
    final d = PackDownloader();
    try {
      return await d.fetchIndex(PackDownloader.normalize(base));
    } finally {
      d.close();
    }
  }

  /// Downloads the chosen packs (resumable, verified), installs each as soon as it is complete and (re)starts the
  /// engine when search data arrives. Reading is usable as soon as the content release is in.
  Future<void> downloadAndInstall(
    String base,
    List<RemotePack> packs, {
    DownloadProgress? onProgress,
    bool Function()? isCancelled,
    void Function(RemotePack pack)? onPack,
  }) async {
    final root = _root;
    if (root == null) throw PackException('unavailable', 'Downloads are not available in this build');
    final uri = PackDownloader.normalize(base);
    final work = Directory('${root.path}/scriptura/downloads')..createSync(recursive: true);
    final lib = EnginePaths.findLibrary(env: _env);
    final d = PackDownloader();
    try {
      final grand = packs.fold<int>(0, (a, p) => a + p.bytes);
      var done = 0;
      // content first (reading needs it), then search data, then the optional index
      const order = {'release': 0, 'engine': 1, 'entities': 2, 'answers': 3, 'topics': 4, 'colbert': 5, 'answer-focus-int8': 6, 'answer-focus-fp16': 6};
      final sorted = [...packs]..sort((a, b) => (order[a.kind] ?? 9).compareTo(order[b.kind] ?? 9));
      for (final p in sorted) {
        onPack?.call(p);
        final dir = await d.download(
          uri,
          p,
          work,
          onProgress: onProgress,
          isCancelled: isCancelled,
          alreadyDone: done,
          grandTotal: grand,
          unpack: lib == null ? null : (zip, out) => Isolate.run(() => _unpackZip(lib, zip.path, out.path)),
        );
        done += p.bytes;
        switch (p.kind) {
          case 'release':
            final m = jsonDecode(File('${dir.path}/manifest.json').readAsStringSync()) as Map<String, dynamic>;
            final names = (m['files'] as Map).keys.cast<String>().toSet();
            await releases.installFromDirectory(dir, include: {...requiredReleaseFiles, if (names.contains('phrase-index.db')) 'phrase-index.db'});
            dir.deleteSync(recursive: true);
            _loadContent();
            notifyListeners();
          case 'engine':
            await enginePacks.adoptVerified(dir);
            await _startEngine();
          case 'entities':
            await entityPacks.adoptVerified(dir);
            await _startEngine();
          case 'topics':
            await topicPacks.adoptVerified(dir);
            await _startEngine();
          case 'answers':
            await answerPacks.adoptVerified(dir);
            _loadAnswers();
            notifyListeners();
          case 'colbert':
            await colbertPacks.adoptVerified(dir);
            await _startEngine();
          case 'answer-focus-int8':
            await focusInt8Packs.adoptVerified(dir);
            await _startEngine();
          case 'answer-focus-fp16':
            await focusFp16Packs.adoptVerified(dir);
            await _startEngine();
          default:
            throw PackException('unknown_kind', 'This host offers a pack this version cannot install (${p.kind}).');
        }
      }
    } finally {
      d.close();
    }
  }

  static void _unpackZip(String library, String zip, String out) {
    try {
      EngineBindings(library).extractZip(zip, out);
    } on EngineOpenException catch (e) {
      throw PackException('unpack_failed', 'Could not unpack the download: ${e.errorJson}');
    }
  }

  // ---- automatic first-run setup -------------------------------------------------------------------------------

  SetupPhase _setup = SetupPhase.idle;
  bool _setupCancel = false;
  bool lastRunIncludedOptional = false;
  bool lastRunIncludedFocus = false;
  double? setupFraction;
  String setupLabel = '';
  String? setupError;

  SetupPhase get setupPhase => _setup;
  bool get setupBusy => _setup == SetupPhase.checking || _setup == SetupPhase.downloading || _setup == SetupPhase.unpacking;

  /// Kinds of data this install still lacks.
  Set<String> get missingData => {
        if (_root != null && activeRelease == null) 'release',
        if (_root != null && _enginePack() == null) 'engine',
        if (_root != null && _entityPack() == null) 'entities',
        if (_root != null && answerPacks.active() == null) 'answers',
        if (_root != null && _colbertPack() == null) 'colbert',
      };

  /// Plain-language status while data is being fetched, else null.
  String? get setupStatus => setupBusy ? setupLabel : null;

  void pauseSetup() => _setupCancel = true;

  static String _today() => DateTime.now().toIso8601String().substring(0, 10);

  /// True when only the optional word-level index is missing and the user has not said "not now".
  bool get offerOptionalIndex => _root != null && missingData.length == 1 && missingData.contains('colbert') && user.pref('index_declined') != '1';

  void declineOptionalIndex() {
    user.setPref('index_declined', '1');
    notifyListeners();
  }

  /// Fetches whatever is missing (scripture text, search data, optional word-level index) from the published address.
  /// Safe to call again: finished files are kept, partial ones resume. Never throws; the outcome is in [setupPhase].
  ///
  /// The optional word-level index (about 3 GB) is only fetched with [includeOptional], which the user asks for: the
  /// app never starts a multi-gigabyte download they did not choose.
  /// Answer focus is fetched only with [includeFocus] (the reader asked), and only the variant this device chose.
  Future<void> ensureData({String? address, bool includeOptional = false, bool includeFocus = false}) async {
    final base = address ?? kDefaultDataAddress;
    if (setupBusy || base.isEmpty) return;
    lastRunIncludedOptional = includeOptional;
    lastRunIncludedFocus = includeFocus;
    final missing = {
      ...(includeOptional ? missingData : (missingData..remove('colbert'))),
      if (includeFocus && _focusKind != null && !focusInstalled) _focusKind!,
    };
    // The topics pack is offered only when the host lists it; with everything else installed, look at most once a day.
    final topicsDue = _root != null && topicPacks.active() == null && user.pref('topics_checked_on') != _today();
    if (missing.isEmpty && !topicsDue) return;
    _setup = SetupPhase.checking;
    _setupCancel = false;
    setupError = null;
    setupFraction = null;
    setupLabel = 'Looking for the scripture data…';
    notifyListeners();
    try {
      final index = await checkHost(base);
      if (topicsDue) user.setPref('topics_checked_on', _today());
      final wanted = index.packs.where((p) => missing.contains(p.kind) || (p.kind == 'topics' && topicsDue)).toList();
      if (wanted.isEmpty) {
        if (missing.isEmpty) {
          _setup = SetupPhase.idle;
          setupLabel = '';
          notifyListeners();
          return;
        }
        throw PackException('nothing_offered', 'The data host does not offer what this app needs.');
      }
      final clock = Stopwatch()..start();
      var lastNotify = -1000;
      String friendly(RemotePack p) => switch (p.kind) {
            'release' => 'scripture text',
            'engine' => 'search data',
            'entities' => 'names of people and places',
            'answers' => 'study questions',
            'topics' => 'topic index',
            'answer-focus-int8' || 'answer-focus-fp16' => 'Answer focus',
            _ => 'word-level index',
          };
      var current = wanted.first;
      await downloadAndInstall(
        base,
        wanted,
        isCancelled: () => _setupCancel,
        onPack: (p) {
          current = p;
          _setup = SetupPhase.downloading;
          setupLabel = 'Downloading ${friendly(p)}…';
          setupFraction = null;
          notifyListeners();
        },
        onProgress: (done, total, file) {
          if (file.startsWith('unpack:')) {
            _setup = SetupPhase.unpacking;
            setupLabel = 'Unpacking ${friendly(current)}…';
            setupFraction = null;
            notifyListeners();
            return;
          }
          _setup = SetupPhase.downloading;
          setupFraction = total == 0 ? null : done / total;
          final gb = done / (1 << 30);
          final have = gb >= 1 ? '${gb.toStringAsFixed(1)} GB' : '${(done / (1 << 20)).round()} MB';
          setupLabel = 'Downloading ${friendly(current)} · $have of ${(total / (1 << 30)).toStringAsFixed(1)} GB';
          if (clock.elapsedMilliseconds - lastNotify > 200) {
            lastNotify = clock.elapsedMilliseconds;
            notifyListeners();
          }
        },
      );
      _setup = SetupPhase.idle;
      setupLabel = '';
    } on PackException catch (e) {
      if (e.code == 'cancelled') {
        _setup = SetupPhase.paused;
      } else {
        _setup = SetupPhase.failed;
        setupError = e.message;
      }
    } on SocketException {
      _setup = SetupPhase.failed;
      setupError = 'Could not reach the download server. Check the internet connection and try again.';
    } on HttpException catch (e) {
      _setup = SetupPhase.failed;
      setupError = 'The download server did not respond properly (${e.message}). Try again in a moment.';
    } on Object catch (e) {
      _setup = SetupPhase.failed;
      setupError = 'Setup could not finish: $e';
    }
    notifyListeners();
  }

  Future<void> installEnginePack(Directory source, {PackProgress? onProgress}) async {
    await enginePacks.installFromDirectory(source, onProgress: onProgress);
    await _startEngine();
  }

  Future<void> installColbertPack(Directory source, {PackProgress? onProgress}) async {
    await colbertPacks.installFromDirectory(source, onProgress: onProgress);
    await _startEngine();
  }

  /// Releases the engine and database handles and waits until they are closed (use before deleting the data directory).
  Future<void> close() async {
    await _search.close();
    _content?.dispose();
    _content = null;
    _answers?.dispose();
    _answers = null;
    _user?.dispose();
    _user = null;
  }

  @override
  void dispose() {
    _search.close();
    _content?.dispose();
    _content = null;
    _user?.dispose();
    _user = null;
    nav.dispose();
    super.dispose();
  }
}
