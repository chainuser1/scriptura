import 'dart:async';
import 'dart:convert';
import 'dart:isolate';

import 'engine_bindings.dart';
import 'search_models.dart';

/// Search backend as the UI sees it. Implementations never expose native pointers; failures are [SearchFailure].
abstract class SearchService {
  /// False when the engine pack is missing or failed to load; [unavailableReason] then explains why.
  bool get available;
  String? get unavailableReason;

  /// Phrase/semantic profiles that need the ColBERT token pack are unavailable until it is installed.
  bool get hasColbertPack;

  /// Allocates a fresh request ID (monotonic). Pass it to [search] and, to abandon the request, to [cancel].
  int nextRequestId();

  Future<SearchResponse> search(SearchRequest request, {int? requestId});
  void cancel(int requestId);
  Future<void> close();
}

/// Used when the engine pack or library is not installed: reading still works, search explains what is missing.
class UnavailableSearchService implements SearchService {
  UnavailableSearchService(this.reason, {this.code = 'missing_pack'});
  final String reason, code;
  int _next = 0;

  @override
  bool get available => false;
  @override
  String? get unavailableReason => reason;
  @override
  bool get hasColbertPack => false;
  @override
  int nextRequestId() => ++_next;
  @override
  Future<SearchResponse> search(SearchRequest request, {int? requestId}) => Future.error(SearchFailure(code, reason));
  @override
  void cancel(int requestId) {}
  @override
  Future<void> close() async {}
}

class _WorkerInit {
  _WorkerInit(this.port, this.library, this.configJson);
  final SendPort port;
  final String library, configJson;
}

void _worker(_WorkerInit init) {
  final inbox = ReceivePort();
  EngineBindings b;
  int handle;
  try {
    b = EngineBindings(init.library);
    handle = b.open(init.configJson);
  } on EngineOpenException catch (e) {
    init.port.send(['error', e.errorJson]);
    return;
  } catch (e) {
    init.port.send(['error', jsonEncode({'error': {'code': 'open_failed', 'message': '$e'}})]);
    return;
  }
  init.port.send(['ready', inbox.sendPort, handle]);
  inbox.listen((m) {
    if (m == 'close') {
      b.close(handle); // releases the SQLite connections and mapped files before the isolate goes away
      init.port.send([-1, 'closed']);
      inbox.close();
      return;
    }
    final msg = m as List;
    init.port.send([msg[0], b.request(handle, msg[1] as String)]);
  });
}

class NativeSearchService implements SearchService {
  NativeSearchService._(this._bindings, this._handle, this._isolate, this._to, this._from, this._sub, this._pending, this.hasColbertPack);

  final EngineBindings _bindings;
  final int _handle;
  final Isolate _isolate;
  final SendPort _to;
  final ReceivePort _from;
  final StreamSubscription<dynamic> _sub;
  final Map<int, Completer<String>> _pending;
  final _cancelled = <int>{};
  int _next = 0;
  var _closed = false;

  @override
  final bool hasColbertPack;

  /// Starts the worker isolate and opens the engine there. Throws [SearchFailure] when it cannot open.
  static Future<NativeSearchService> open({required String libraryPath, required Map<String, dynamic> config}) async {
    final from = ReceivePort();
    final ready = Completer<List<dynamic>>();
    final pending = <int, Completer<String>>{};
    final sub = from.listen((m) {
      final msg = m as List;
      if (!ready.isCompleted) {
        ready.complete(msg);
      } else {
        pending.remove(msg[0] as int)?.complete(msg[1] as String);
      }
    });
    final isolate = await Isolate.spawn(_worker, _WorkerInit(from.sendPort, libraryPath, jsonEncode(config)));
    final first = await ready.future;
    if (first[0] == 'error') {
      await sub.cancel();
      from.close();
      isolate.kill(priority: Isolate.immediate);
      final e = (jsonDecode(first[1] as String) as Map)['error'] as Map;
      throw SearchFailure(e['code'] as String, e['message'] as String);
    }
    return NativeSearchService._(EngineBindings(libraryPath), first[2] as int, isolate, first[1] as SendPort, from, sub, pending,
        config['pack_dir'] != null);
  }

  @override
  bool get available => !_closed;
  @override
  String? get unavailableReason => _closed ? 'The search engine was closed' : null;

  @override
  int nextRequestId() => ++_next;

  @override
  Future<SearchResponse> search(SearchRequest request, {int? requestId}) async {
    if (_closed) throw SearchFailure('missing_pack', 'The search engine was closed');
    final id = requestId ?? nextRequestId();
    final done = Completer<String>();
    _pending[id] = done;
    _to.send([id, jsonEncode(request.toJson(id))]);
    final j = jsonDecode(await done.future) as Map<String, dynamic>;
    if (_cancelled.remove(id)) throw SearchFailure('cancelled', 'request cancelled');
    final err = j['error'] as Map?;
    if (err != null) throw SearchFailure(err['code'] as String, err['message'] as String);
    return SearchResponse.fromJson(j);
  }

  @override
  void cancel(int requestId) {
    if (_closed) return;
    if (_pending.containsKey(requestId)) {
      _cancelled.add(requestId);
      _bindings.cancel(_handle, requestId); // thread-safe flag in the engine; honoured at the next checkpoint
    }
  }

  @override
  Future<void> close() async {
    if (_closed) return;
    _closed = true;
    final closed = Completer<String>();
    _pending[-1] = closed;
    _to.send('close');
    await closed.future.timeout(const Duration(seconds: 10), onTimeout: () => 'timeout');
    await _sub.cancel();
    _from.close();
    _isolate.kill();
  }
}
