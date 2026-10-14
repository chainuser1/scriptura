import 'dart:convert';
import 'dart:ffi';

import 'package:ffi/ffi.dart';

typedef _OpenC = Pointer<Void> Function(Pointer<Utf8>, Pointer<Pointer<Utf8>>);
typedef _OpenD = Pointer<Void> Function(Pointer<Utf8>, Pointer<Pointer<Utf8>>);
typedef _RequestC = Pointer<Utf8> Function(Pointer<Void>, Pointer<Utf8>);
typedef _RequestD = Pointer<Utf8> Function(Pointer<Void>, Pointer<Utf8>);
typedef _CancelC = Void Function(Pointer<Void>, Uint64);
typedef _CancelD = void Function(Pointer<Void>, int);
typedef _CloseC = Void Function(Pointer<Void>);
typedef _CloseD = void Function(Pointer<Void>);
typedef _FreeC = Void Function(Pointer<Utf8>);
typedef _FreeD = void Function(Pointer<Utf8>);
typedef _ExtractC = Pointer<Utf8> Function(Pointer<Utf8>, Pointer<Utf8>);
typedef _ExtractD = Pointer<Utf8> Function(Pointer<Utf8>, Pointer<Utf8>);
typedef _VersionC = Pointer<Utf8> Function();
typedef _VersionD = Pointer<Utf8> Function();

/// Thin binding of the engine's C ABI (engine/src/capi.rs). JSON in, JSON out; strings returned by the engine are
/// copied and released here, so callers never see a native pointer.
class EngineBindings {
  EngineBindings(String libraryPath) : this._(DynamicLibrary.open(libraryPath));

  EngineBindings._(DynamicLibrary lib)
      : _open = lib.lookupFunction<_OpenC, _OpenD>('se_open'),
        _request = lib.lookupFunction<_RequestC, _RequestD>('se_request'),
        _cancel = lib.lookupFunction<_CancelC, _CancelD>('se_cancel'),
        _close = lib.lookupFunction<_CloseC, _CloseD>('se_close'),
        _free = lib.lookupFunction<_FreeC, _FreeD>('se_free_string'),
        _extract = lib.lookupFunction<_ExtractC, _ExtractD>('se_extract_zip'),
        _version = lib.lookupFunction<_VersionC, _VersionD>('se_version');

  final _OpenD _open;
  final _RequestD _request;
  final _CancelD _cancel;
  final _CloseD _close;
  final _FreeD _free;
  final _ExtractD _extract;
  final _VersionD _version;

  String get version => _version().toDartString();

  /// Returns the engine handle address, or throws with the engine's error JSON.
  int open(String configJson) {
    final cfg = configJson.toNativeUtf8();
    final err = calloc<Pointer<Utf8>>();
    try {
      final h = _open(cfg, err);
      if (h == nullptr) {
        final p = err.value;
        final msg = p == nullptr ? '{"error":{"code":"open_failed","message":"unknown"}}' : p.toDartString();
        if (p != nullptr) _free(p);
        throw EngineOpenException(msg);
      }
      return h.address;
    } finally {
      calloc.free(cfg);
      calloc.free(err);
    }
  }

  String request(int handle, String requestJson) {
    final req = requestJson.toNativeUtf8();
    try {
      final out = _request(Pointer<Void>.fromAddress(handle), req);
      final s = out.toDartString();
      _free(out);
      return s;
    } finally {
      calloc.free(req);
    }
  }

  /// Streams a pack archive onto disk (top-level folder stripped); returns the file count. Throws [EngineOpenException]
  /// with the engine's error JSON. Blocking: run it off the UI isolate.
  int extractZip(String zipPath, String outDir) {
    final z = zipPath.toNativeUtf8();
    final o = outDir.toNativeUtf8();
    try {
      final out = _extract(z, o);
      final text = out.toDartString();
      _free(out);
      final j = jsonDecode(text) as Map<String, dynamic>;
      if (j.containsKey('error')) throw EngineOpenException(text);
      return j['files'] as int;
    } finally {
      calloc.free(z);
      calloc.free(o);
    }
  }

  void cancel(int handle, int requestId) => _cancel(Pointer<Void>.fromAddress(handle), requestId);

  void close(int handle) => _close(Pointer<Void>.fromAddress(handle));
}

class EngineOpenException implements Exception {
  EngineOpenException(this.errorJson);
  final String errorJson;
  @override
  String toString() => 'EngineOpenException($errorJson)';
}
