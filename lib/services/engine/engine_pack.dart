import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:path/path.dart' as p;

/// An installed, verified directory of engine data: the engine pack (encoder, tokenizer, head, retrieval indexes,
/// people index) or the optional ColBERT token pack. Both carry a manifest listing every file with size and SHA-256.
class InstalledPack {
  InstalledPack(this.dir, this.manifest);
  final Directory dir;
  final Map<String, dynamic> manifest;
  String path(String rel) => '${dir.path}/$rel';
  bool has(String rel) => File(path(rel)).existsSync();
}

class PackException implements Exception {
  PackException(this.code, this.message);
  final String code, message;
  @override
  String toString() => 'PackException($code): $message';
}

class _DigestSink implements Sink<Digest> {
  late Digest digest;
  @override
  void add(Digest data) => digest = data;
  @override
  void close() {}
}

typedef PackProgress = void Function(int doneBytes, int totalBytes, String file);

enum PackKind {
  engine('engine-pack-v1', 'engine-pack'),
  colbert('colbert-pack-v1', 'colbert-pack'),
  entities('entities-pack-v1', 'entities-pack'),
  answers('answers-pack-v1', 'answers-pack'),
  topics('topics-pack-v1', 'topics-pack'),
  focusInt8('answer-focus-int8-v1', 'answer-focus-int8'),
  focusFp16('answer-focus-fp16-v1', 'answer-focus-fp16'),
  apollosFp16('apollos-fp16-v1', 'apollos-fp16'),
  apollosInt8('apollos-int8-v1', 'apollos-int8'),
  priscillaInt8('priscilla-int8-v1', 'priscilla-int8'),
  aquilaInt8('aquila-int8-v1', 'aquila-int8');

  const PackKind(this.format, this.dirName);
  final String format, dirName;
}

class PackStore {
  PackStore(this.root, this.kind);
  final Directory root; // e.g. <support>/scriptura
  final PackKind kind;

  Directory get _dir => Directory('${root.path}/${kind.dirName}');

  /// name -> (bytes, sha256), from either manifest shape ('files' or 'shards').
  static Map<String, ({int bytes, String sha})> listed(Map<String, dynamic> m) {
    final src = (m['files'] ?? m['shards']) as Map<String, dynamic>?;
    if (src == null) throw PackException('manifest_invalid', 'manifest lists no files');
    return {for (final e in src.entries) e.key: (bytes: (e.value as Map)['bytes'] as int, sha: (e.value as Map)['sha256'] as String)};
  }

  /// Cheap check: install marker, every listed file present with its recorded size.
  InstalledPack? active() {
    try {
      final marker = File('${_dir.path}/install.json');
      if (!marker.existsSync()) return null;
      final m = jsonDecode(marker.readAsStringSync()) as Map<String, dynamic>;
      if (m['format'] != kind.format) return null;
      for (final e in listed(m).entries) {
        final f = File('${_dir.path}/${e.key}');
        if (!f.existsSync() || f.lengthSync() != e.value.bytes) return null;
      }
      return InstalledPack(_dir, m);
    } catch (_) {
      return null;
    }
  }

  /// Activates a directory whose files were already verified (for example by the downloader): size-checks them
  /// against its manifest, writes the install marker last and renames it into place.
  Future<InstalledPack> adoptVerified(Directory staged) async {
    final manifestFile = File('${staged.path}/manifest.json');
    if (!manifestFile.existsSync()) throw PackException('manifest_missing', 'The download has no manifest.json');
    final m = jsonDecode(await manifestFile.readAsString()) as Map<String, dynamic>;
    if (m['format'] != kind.format) throw PackException('wrong_kind', 'Expected ${kind.format}, found ${m['format']}');
    final files = listed(m);
    for (final e in files.entries) {
      final f = File('${staged.path}/${e.key}');
      if (!f.existsSync() || f.lengthSync() != e.value.bytes) throw PackException('size_mismatch', '${e.key} is missing or the wrong size');
    }
    // Compare by path relative to `staged`, normalized with `package:path` -- `Directory.listSync()`
    // returns backslash-separated paths on Windows while manifest keys and hand-built paths use `/`,
    // so a raw string/`File.path` comparison here silently never matches and defeats this guard.
    final keep = files.keys.map(p.normalize).toSet();
    for (final f in staged.listSync(recursive: true).whereType<File>()) {
      final rel = p.normalize(p.relative(f.path, from: staged.path));
      // Downloader bookkeeping only -- never a file the manifest actually lists (e.g. Apollos's own
      // real `converted.ok`), which a blanket "*.ok" match would otherwise delete.
      if ((f.path.endsWith('.ok') || f.path.endsWith('.part')) && !keep.contains(rel)) f.deleteSync();
    }
    await File('${staged.path}/install.json').writeAsString(jsonEncode(m));
    if (_dir.existsSync()) _dir.deleteSync(recursive: true);
    _dir.parent.createSync(recursive: true);
    staged.renameSync(_dir.path);
    return active()!;
  }

  /// Verifies every file's size and SHA-256 while copying into a staging directory, then renames into place. The
  /// install marker is written last, so an interrupted install is never mistaken for a usable pack.
  Future<InstalledPack> installFromDirectory(Directory source, {PackProgress? onProgress, bool Function()? isCancelled}) async {
    final manifestFile = File('${source.path}/manifest.json');
    if (!manifestFile.existsSync()) throw PackException('manifest_missing', 'No manifest.json in ${source.path}');
    final m = jsonDecode(await manifestFile.readAsString()) as Map<String, dynamic>;
    if (m['format'] != kind.format) {
      throw PackException('wrong_kind', 'Expected ${kind.format}, found ${m['format']}');
    }
    final files = listed(m);
    final total = files.values.fold<int>(0, (a, f) => a + f.bytes);
    final staging = Directory('${root.path}/staging/${kind.dirName}-${DateTime.now().microsecondsSinceEpoch}');
    staging.createSync(recursive: true);
    var done = 0;
    try {
      for (final e in files.entries) {
        if (isCancelled?.call() ?? false) throw PackException('cancelled', 'Installation cancelled');
        final src = File('${source.path}/${e.key}');
        if (!src.existsSync()) throw PackException('file_missing', '${e.key} is not in the import directory');
        if (src.lengthSync() != e.value.bytes) {
          throw PackException('size_mismatch', '${e.key} has ${src.lengthSync()} bytes, expected ${e.value.bytes}');
        }
        final dst = File('${staging.path}/${e.key}');
        dst.parent.createSync(recursive: true);
        final sink = dst.openWrite();
        final out = _DigestSink();
        final hasher = sha256.startChunkedConversion(out);
        await for (final chunk in src.openRead()) {
          hasher.add(chunk);
          sink.add(chunk);
          done += chunk.length;
          onProgress?.call(done, total, e.key);
        }
        hasher.close();
        await sink.flush();
        await sink.close();
        if (out.digest.toString() != e.value.sha) {
          throw PackException('hash_mismatch', '${e.key} failed SHA-256 verification');
        }
      }
      await File('${staging.path}/install.json').writeAsString(jsonEncode(m));
      if (_dir.existsSync()) _dir.deleteSync(recursive: true);
      _dir.parent.createSync(recursive: true);
      staging.renameSync(_dir.path);
    } catch (_) {
      if (staging.existsSync()) staging.deleteSync(recursive: true);
      rethrow;
    }
    return active()!;
  }
}

/// Everything needed to open the engine, resolved from installed packs. Environment overrides are for development
/// and tests only (they point at already-built directories and skip installation).
class EnginePaths {
  EnginePaths(
      {required this.libraryPath,
      required this.engine,
      this.colbert,
      this.phraseDb,
      this.catalogDb,
      this.entitiesDb,
      this.topicsDb,
      this.focus,
      this.focusGpu = false,
      this.focusFamily});
  final String libraryPath;
  final InstalledPack engine;
  final InstalledPack? colbert;
  final String? phraseDb, catalogDb;

  /// People, places and groups index from the entities pack; falls back to the engine pack's own `entities.db`.
  final String? entitiesDb;

  /// Optional topics pack database: adds the topic lane to similar verses.
  final String? topicsDb;

  /// Answer focus pack (model.onnx, tokenizer.json), run on the graphics chip when [focusGpu].
  final InstalledPack? focus;
  final bool focusGpu;

  /// Which model family [focus] is ('ezra' or 'apollos'); an engine build that predates this field treats an
  /// absent `focus_family` as Ezra, so omitting or leaving this null is backward compatible.
  final String? focusFamily;

  /// Engine configuration JSON (see engine/src/engine.rs `Config`).
  Map<String, dynamic> config() {
    final m = engine.manifest;
    return {
      'retrieval_dir': engine.path('retrieval'),
      'head_npz': engine.path('head.npz'),
      'encoder_model': engine.path(m['encoder_file'] as String),
      'tokenizer_json': engine.path('tokenizer.json'),
      if (colbert != null && colbert!.has('shard-0000.vec.npy')) 'pack_dir': colbert!.dir.path,
      if (phraseDb != null) 'phrase_db': phraseDb,
      if (topicsDb != null) 'topics_db': topicsDb,
      if (focus != null) ...{
        'focus_model': focus!.path('model.onnx'),
        'focus_tokenizer': focus!.path('tokenizer.json'),
        'focus_device': focusGpu ? 'gpu' : 'cpu',
        'focus_family': focusFamily ?? 'ezra',
      },
      // no volume wins only for being itself (engine/src/balance.rs); strength chosen in tool/volume_balance.py
      'volume_balance': 0.75,
      if (catalogDb != null) 'catalog_db': catalogDb,
      if (entitiesDb != null) 'entities_db': entitiesDb else if (engine.has('entities.db')) 'entities_db': engine.path('entities.db'),
      'profiles': m['profiles'],
      'default_profile': m['default_profile'],
      'fallback_without_thread': m['fallback_without_thread'],
      if (Platform.isAndroid) 'ort_library': 'libonnxruntime.so',
      // Apollos's int8 pack is batch_size=1 (fixed at export), so every candidate is its own session.run() --
      // more intra-op threads per run is a real, free speedup there. The device's actual core count, not a
      // guessed constant: most phones/laptops have well over the old hardcoded 4/2.
      'threads': Platform.numberOfProcessors,
      'identity': m['identity'],
    };
  }

  static String? findLibrary({Map<String, String>? env}) {
    final e = env ?? Platform.environment;
    final candidates = <String>[
      if (e['SCRIPTURA_ENGINE_LIB'] != null) e['SCRIPTURA_ENGINE_LIB']!,
      if (Platform.isWindows) '${File(Platform.resolvedExecutable).parent.path}\\scripture_engine.dll',
      if (Platform.isAndroid) 'libscripture_engine.so',
      'engine/target/release/scripture_engine.dll',
    ];
    for (final c in candidates) {
      if (c == 'libscripture_engine.so' || File(c).existsSync()) return c;
    }
    return null;
  }
}
