import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/services/artifacts/release_store.dart';

Directory makeSource({bool corrupt = false}) {
  final d = Directory.systemTemp.createTempSync('src');
  final bytes = utf8.encode('hello content');
  File('${d.path}/scriptures_genome.db').writeAsBytesSync(corrupt ? utf8.encode('HELLO content') : bytes);
  File('${d.path}/manifest.json').writeAsStringSync(jsonEncode({
    'release': 'rel-1',
    'files': {
      'scriptures_genome.db': {'bytes': bytes.length, 'sha256': sha256.convert(bytes).toString()},
    },
  }));
  return d;
}

void main() {
  test('verified import is copied into a versioned directory and activated', () async {
    final store = ReleaseStore(Directory.systemTemp.createTempSync('root'));
    expect(store.active(), isNull);
    final rel = await store.installFromDirectory(makeSource(), include: {'scriptures_genome.db'});
    expect(rel.id, 'rel-1');
    expect(File(rel.path('scriptures_genome.db')).readAsStringSync(), 'hello content');
    expect(store.active()!.id, 'rel-1');
  });

  test('a corrupted file is rejected and the previous release stays active', () async {
    final store = ReleaseStore(Directory.systemTemp.createTempSync('root'));
    await store.installFromDirectory(makeSource(), include: {'scriptures_genome.db'});
    await expectLater(
      store.installFromDirectory(makeSource(corrupt: true), include: {'scriptures_genome.db'}),
      throwsA(isA<ReleaseException>().having((e) => e.code, 'code', 'hash_mismatch')),
    );
    expect(store.active()!.id, 'rel-1');
  });

  test('missing manifest and missing file have distinct codes', () async {
    final store = ReleaseStore(Directory.systemTemp.createTempSync('root'));
    final empty = Directory.systemTemp.createTempSync('empty');
    await expectLater(store.installFromDirectory(empty, include: {'x'}),
        throwsA(isA<ReleaseException>().having((e) => e.code, 'code', 'manifest_missing')));
    final src = makeSource();
    await expectLater(store.installFromDirectory(src, include: {'questions_genome.db'}),
        throwsA(isA<ReleaseException>().having((e) => e.code, 'code', 'file_missing')));
  });

  test('a damaged active.json reads as not installed rather than crashing', () {
    final root = Directory.systemTemp.createTempSync('root');
    File('${root.path}/active.json').writeAsStringSync('{not json');
    expect(ReleaseStore(root).active(), isNull);
  });

  test('active release whose file was truncated is treated as not installed', () async {
    final root = Directory.systemTemp.createTempSync('root');
    final store = ReleaseStore(root);
    final rel = await store.installFromDirectory(makeSource(), include: {'scriptures_genome.db'});
    File(rel.path('scriptures_genome.db')).writeAsBytesSync([1, 2, 3]);
    expect(store.active(), isNull);
  });
}
