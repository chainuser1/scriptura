import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/services/engine/engine_pack.dart';

Directory makePack(Directory parent, String format, Map<String, List<int>> files, {String key = 'files'}) {
  final d = Directory('${parent.path}/src-${files.length}-$format')..createSync(recursive: true);
  final listed = <String, dynamic>{};
  files.forEach((name, bytes) {
    final f = File('${d.path}/$name')..parent.createSync(recursive: true);
    f.writeAsBytesSync(bytes);
    listed[name] = {'bytes': bytes.length, 'sha256': sha256.convert(bytes).toString()};
  });
  File('${d.path}/manifest.json').writeAsStringSync(jsonEncode({'format': format, key: listed, 'encoder_file': 'a.bin'}));
  return d;
}

void main() {
  late Directory tmp;
  setUp(() => tmp = Directory.systemTemp.createTempSync('packstore-'));
  tearDown(() => tmp.deleteSync(recursive: true));

  test('installs a verified pack, reports progress, and survives a restart', () async {
    final src = makePack(tmp, 'engine-pack-v1', {'a.bin': List.filled(1000, 7), 'retrieval/b.bin': List.filled(10, 1)});
    final store = PackStore(Directory('${tmp.path}/app'), PackKind.engine);
    expect(store.active(), isNull);
    var last = 0;
    final p = await store.installFromDirectory(src, onProgress: (d, t, f) => last = d);
    expect(last, 1010);
    expect(p.has('retrieval/b.bin'), isTrue);
    expect(PackStore(Directory('${tmp.path}/app'), PackKind.engine).active(), isNotNull); // new instance = restart
  });

  test('a corrupted file is refused and nothing is activated', () async {
    final src = makePack(tmp, 'engine-pack-v1', {'a.bin': List.filled(100, 7)});
    File('${src.path}/a.bin').writeAsBytesSync(List.filled(100, 8)); // same size, different content
    final store = PackStore(Directory('${tmp.path}/app'), PackKind.engine);
    await expectLater(store.installFromDirectory(src), throwsA(isA<PackException>().having((e) => e.code, 'code', 'hash_mismatch')));
    expect(store.active(), isNull);
    expect(Directory('${tmp.path}/app/staging').listSync(), isEmpty, reason: 'staging is cleaned up');
  });

  test('wrong size, missing file, wrong kind and missing manifest are distinct errors', () async {
    final store = PackStore(Directory('${tmp.path}/app'), PackKind.engine);
    final a = makePack(tmp, 'engine-pack-v1', {'a.bin': List.filled(10, 1)});
    File('${a.path}/a.bin').writeAsBytesSync(List.filled(11, 1));
    await expectLater(store.installFromDirectory(a), throwsA(isA<PackException>().having((e) => e.code, 'code', 'size_mismatch')));
    File('${a.path}/a.bin').deleteSync();
    await expectLater(store.installFromDirectory(a), throwsA(isA<PackException>().having((e) => e.code, 'code', 'file_missing')));
    final c = makePack(tmp, 'colbert-pack-v1', {'shard-0000.vec.npy': [1, 2, 3]}, key: 'shards');
    await expectLater(store.installFromDirectory(c), throwsA(isA<PackException>().having((e) => e.code, 'code', 'wrong_kind')));
    await expectLater(store.installFromDirectory(Directory('${tmp.path}/nothing')),
        throwsA(isA<PackException>().having((e) => e.code, 'code', 'manifest_missing')));
  });

  test('the colbert manifest shape (shards) installs under its own kind', () async {
    final c = makePack(tmp, 'colbert-pack-v1', {'shard-0000.vec.npy': [1, 2, 3], 'shard-0000.cnt.npy': [4]}, key: 'shards');
    final store = PackStore(Directory('${tmp.path}/app'), PackKind.colbert);
    final p = await store.installFromDirectory(c);
    expect(p.has('shard-0000.vec.npy'), isTrue);
  });

  test('a replaced or truncated file after install makes the pack inactive', () async {
    final src = makePack(tmp, 'engine-pack-v1', {'a.bin': List.filled(50, 7)});
    final store = PackStore(Directory('${tmp.path}/app'), PackKind.engine);
    await store.installFromDirectory(src);
    File('${tmp.path}/app/engine-pack/a.bin').writeAsBytesSync([1]);
    expect(store.active(), isNull);
  });

  test('cancelling stops the install and leaves no pack behind', () async {
    final src = makePack(tmp, 'engine-pack-v1', {'a.bin': List.filled(50, 7), 'b.bin': List.filled(50, 8)});
    final store = PackStore(Directory('${tmp.path}/app'), PackKind.engine);
    var n = 0;
    await expectLater(store.installFromDirectory(src, isCancelled: () => ++n > 1),
        throwsA(isA<PackException>().having((e) => e.code, 'code', 'cancelled')));
    expect(store.active(), isNull);
  });
}
