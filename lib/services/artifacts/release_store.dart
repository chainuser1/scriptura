import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';

/// Files a usable release must contain: the compact content database (English text = KJV) and its catalog.
const requiredReleaseFiles = {'content.db', 'catalog.db'};

class ReleaseException implements Exception {
  ReleaseException(this.code, this.message);
  final String code, message;
  @override
  String toString() => 'ReleaseException($code): $message';
}

class ActiveRelease {
  ActiveRelease(this.id, this.dir);
  final String id;
  final Directory dir;
  String path(String fileName) => '${dir.path}/$fileName';
}

class ReleaseStore {
  ReleaseStore(this.root);
  final Directory root;

  File get _activeFile => File('${root.path}/active.json');

  /// Cheap check (existence + byte size recorded at install). Full hashing happens only at install.
  ActiveRelease? active() {
    try {
      final j = jsonDecode(_activeFile.readAsStringSync()) as Map<String, dynamic>;
      final id = j['release'] as String;
      final dir = Directory('${root.path}/content/$id');
      final files = (j['files'] as Map<String, dynamic>);
      for (final e in files.entries) {
        final f = File('${dir.path}/${e.key}');
        if (!f.existsSync() || f.lengthSync() != (e.value as Map)['bytes']) return null;
      }
      return ActiveRelease(id, dir);
    } catch (_) {
      return null;
    }
  }

  Future<String> _sha(File f) async => (await sha256.bind(f.openRead()).first).toString();

  Future<ActiveRelease> installFromDirectory(Directory source, {required Set<String> include}) async {
    final manifestFile = File('${source.path}/manifest.json');
    if (!manifestFile.existsSync()) {
      throw ReleaseException('manifest_missing', 'No manifest.json in ${source.path}');
    }
    final m = jsonDecode(manifestFile.readAsStringSync()) as Map<String, dynamic>;
    final id = m['release'] as String;
    final listed = (m['files'] as Map<String, dynamic>).cast<String, Map<String, dynamic>>();

    for (final name in include) {
      final entry = listed[name];
      final f = File('${source.path}/$name');
      if (entry == null || !f.existsSync()) {
        throw ReleaseException('file_missing', '$name is not in the import directory or its manifest');
      }
      if (f.lengthSync() != entry['bytes']) {
        throw ReleaseException('size_mismatch', '$name has ${f.lengthSync()} bytes, expected ${entry['bytes']}');
      }
      if (await _sha(f) != entry['sha256']) {
        throw ReleaseException('hash_mismatch', '$name failed SHA-256 verification');
      }
    }

    // Stage into a private directory, then rename into place; the active pointer flips last.
    final staging = Directory('${root.path}/staging/$id-${DateTime.now().microsecondsSinceEpoch}');
    staging.createSync(recursive: true);
    for (final name in include) {
      await File('${source.path}/$name').copy('${staging.path}/$name');
    }
    final finalDir = Directory('${root.path}/content/$id');
    finalDir.parent.createSync(recursive: true);
    if (finalDir.existsSync()) finalDir.deleteSync(recursive: true); // same release id re-import only
    staging.renameSync(finalDir.path);

    final pointer = File('${root.path}/active.json.tmp');
    pointer.writeAsStringSync(jsonEncode({
      'release': id,
      'files': {for (final n in include) n: {'bytes': File('${finalDir.path}/$n').lengthSync()}},
    }));
    pointer.renameSync(_activeFile.path); // atomic replace
    return ActiveRelease(id, finalDir);
  }
}
