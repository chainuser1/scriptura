import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';

import 'engine_pack.dart';

/// What a host offers: `index.json` at the base address lists every pack with each file's size and SHA-256
/// (written by tool/prepare_hosting.py). Anything downloaded is verified against it before it is used.
class RemoteFile {
  RemoteFile(this.path, this.bytes, this.sha256);
  final String path, sha256;
  final int bytes;
}

class RemotePack {
  RemotePack({
    required this.id,
    required this.kind,
    required this.title,
    required this.version,
    required this.folder,
    required this.optional,
    required this.requires,
    required this.note,
    required this.files,
    this.archive,
  });

  final String id, kind, title, version, folder, note;
  final bool optional;
  final List<String> requires;
  final List<RemoteFile> files;

  /// A single `.zip` holding the whole pack (top-level folder `<folder>/`): downloaded as one verified file, then
  /// unpacked. `files` still lists what must be present afterwards.
  final RemoteFile? archive;

  /// Bytes to transfer: the archive when there is one, otherwise every file.
  int get bytes => archive?.bytes ?? files.fold(0, (a, f) => a + f.bytes);

  factory RemotePack.fromJson(Map<String, dynamic> j) => RemotePack(
        id: j['id'] as String,
        kind: j['kind'] as String,
        title: j['title'] as String,
        version: '${j['version']}',
        folder: j['folder'] as String,
        optional: j['optional'] as bool? ?? false,
        requires: [for (final r in (j['requires'] as List? ?? const [])) r as String],
        note: j['note'] as String? ?? '',
        files: [
          for (final e in (j['files'] as Map<String, dynamic>).entries)
            RemoteFile(e.key, (e.value as Map)['bytes'] as int, (e.value as Map)['sha256'] as String)
        ],
        archive: j['archive'] is Map
            ? RemoteFile((j['archive'] as Map)['name'] as String, (j['archive'] as Map)['bytes'] as int, (j['archive'] as Map)['sha256'] as String)
            : null,
      );
}

class RemoteIndex {
  RemoteIndex(this.packs);
  final List<RemotePack> packs;

  factory RemoteIndex.parse(String body) {
    final j = jsonDecode(body) as Map<String, dynamic>;
    if (j['format'] != 'scriptura-index-v1') throw PackException('index_invalid', 'This address does not offer Scriptura data.');
    return RemoteIndex([for (final p in (j['packs'] as List)) RemotePack.fromJson((p as Map).cast<String, dynamic>())]);
  }
}

typedef DownloadProgress = void Function(int doneBytes, int totalBytes, String file);

/// Resumable, verifying HTTP downloader. Interrupted downloads continue from the bytes already on disk; a finished file
/// is accepted only when its SHA-256 matches the index. No credentials are ever sent.
class PackDownloader {
  PackDownloader({HttpClient? client}) : _http = client ?? HttpClient()..connectionTimeout = const Duration(seconds: 20);
  final HttpClient _http;

  void close() => _http.close(force: true);

  static Uri normalize(String base) {
    var s = base.trim();
    if (!s.endsWith('/')) s = '$s/';
    final u = Uri.parse(s);
    if (u.scheme != 'https' && u.scheme != 'http') throw PackException('bad_address', 'Enter an address that starts with https://');
    return u;
  }

  Future<RemoteIndex> fetchIndex(Uri base) async {
    final req = await _http.getUrl(base.resolve('index.json'));
    final res = await req.close();
    if (res.statusCode != 200) {
      await res.drain<void>();
      throw PackException('index_unavailable', 'The address answered ${res.statusCode}; it does not look like a data host.');
    }
    return RemoteIndex.parse(await res.transform(utf8.decoder).join());
  }

  /// Downloads [pack] into [workDir]/[pack.id], resuming where it left off, and returns that directory. A pack with an
  /// archive is fetched as one verified zip and handed to [unpack] (which extracts it into the directory); otherwise
  /// every file is fetched and verified on its own.
  Future<Directory> download(
    Uri base,
    RemotePack pack,
    Directory workDir, {
    DownloadProgress? onProgress,
    bool Function()? isCancelled,
    int alreadyDone = 0,
    int? grandTotal,
    Future<void> Function(File zip, Directory out)? unpack,
  }) async {
    final dir = Directory('${workDir.path}/${pack.id}');
    final total = grandTotal ?? pack.bytes;
    final archive = pack.archive;
    if (archive != null) {
      if (unpack == null) throw PackException('unsupported', 'This build cannot unpack ${pack.title}.');
      final zip = File('${workDir.path}/${archive.path}');
      await _fetch(base.resolve(archive.path), zip, archive.bytes, archive.sha256, onProgress, isCancelled, alreadyDone, total);
      onProgress?.call(alreadyDone + archive.bytes, total, 'unpack:${pack.id}');
      if (dir.existsSync()) dir.deleteSync(recursive: true);
      dir.createSync(recursive: true);
      try {
        await unpack(zip, dir);
        for (final f in pack.files) {
          final out = File('${dir.path}/${f.path}');
          if (!out.existsSync() || out.lengthSync() != f.bytes) {
            throw PackException('unpack_incomplete', '${f.path} is missing or the wrong size after unpacking.');
          }
        }
      } catch (_) {
        if (dir.existsSync()) dir.deleteSync(recursive: true);
        rethrow;
      }
      zip.deleteSync();
      File('${zip.path}.ok').deleteSync();
      return dir;
    }
    dir.createSync(recursive: true);
    var done = alreadyDone;
    for (final f in pack.files) {
      await _fetch(base.resolve('${pack.folder}/${f.path}'), File('${dir.path}/${f.path}'), f.bytes, f.sha256, onProgress, isCancelled, done, total);
      done += f.bytes;
    }
    return dir;
  }

  /// One resumable, verified file. A finished file is recognised by its `.ok` marker, so a repeat call is instant.
  Future<void> _fetch(Uri url, File target, int bytes, String sha, DownloadProgress? onProgress, bool Function()? isCancelled,
      int done, int total) async {
    final name = target.uri.pathSegments.last;
    if (isCancelled?.call() ?? false) throw PackException('cancelled', 'Download cancelled');
    target.parent.createSync(recursive: true);
    final marker = File('${target.path}.ok');
    if (target.existsSync() && marker.existsSync() && marker.readAsStringSync() == sha && target.lengthSync() == bytes) {
      onProgress?.call(done + bytes, total, name);
      return;
    }
    final part = File('${target.path}.part');
    var have = part.existsSync() ? part.lengthSync() : 0;
    if (have > bytes) {
      part.deleteSync();
      have = 0;
    }
    if (have < bytes) {
      final req = await _http.getUrl(url);
      if (have > 0) req.headers.set(HttpHeaders.rangeHeader, 'bytes=$have-');
      final res = await req.close();
      if (res.statusCode == 416 && have == bytes) {
        await res.drain<void>();
      } else if (res.statusCode != 200 && res.statusCode != 206) {
        await res.drain<void>();
        throw PackException('download_failed', '$name: the host answered ${res.statusCode}');
      } else {
        final append = res.statusCode == 206 && have > 0;
        if (!append) have = 0; // the host ignored the range: start the file again
        final sink = part.openWrite(mode: append ? FileMode.append : FileMode.write);
        var got = have;
        try {
          await for (final chunk in res) {
            if (isCancelled?.call() ?? false) {
              await sink.flush();
              await sink.close();
              throw PackException('cancelled', 'Download cancelled');
            }
            sink.add(chunk);
            got += chunk.length;
            onProgress?.call(done + got, total, name);
          }
          await sink.flush();
        } finally {
          await sink.close();
        }
      }
    }
    if (part.lengthSync() != bytes) {
      throw PackException('incomplete', '$name is ${part.lengthSync()} bytes, expected $bytes. Try again to resume.');
    }
    final digest = (await sha256.bind(part.openRead()).first).toString();
    if (digest != sha) {
      part.deleteSync();
      throw PackException('hash_mismatch', '$name failed verification and was discarded. Try again.');
    }
    if (target.existsSync()) target.deleteSync();
    part.renameSync(target.path);
    marker.writeAsStringSync(sha);
    onProgress?.call(done + bytes, total, name);
  }
}
