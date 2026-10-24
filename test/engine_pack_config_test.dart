import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/services/engine/engine_pack.dart';

void main() {
  test('the engine config turns volume balance on at the measured strength', () {
    final engine = InstalledPack(Directory('pack'), {
      'encoder_file': 'encoder.onnx',
      'profiles': <String, dynamic>{},
      'default_profile': 'compass',
      'fallback_without_thread': 'compass',
      'identity': <String, dynamic>{},
    });
    final cfg = EnginePaths(libraryPath: 'engine.dll', engine: engine).config();
    // tool/volume_balance.py STRENGTH, chosen by the Task 1 rule (docs/superpowers/plans/2026-10-14-volume-balance.md)
    expect(cfg['volume_balance'], 0.75);
  });

  test('the engine config uses the device\'s real core count, not a guessed constant', () {
    final engine = InstalledPack(Directory('pack'), {
      'encoder_file': 'encoder.onnx',
      'profiles': <String, dynamic>{},
      'default_profile': 'compass',
      'fallback_without_thread': 'compass',
      'identity': <String, dynamic>{},
    });
    final cfg = EnginePaths(libraryPath: 'engine.dll', engine: engine).config();
    expect(cfg['threads'], Platform.numberOfProcessors);
  });

  test('priscillaInt8 pack kind has the expected format and directory name', () {
    expect(PackKind.priscillaInt8.format, 'priscilla-int8-v1');
    expect(PackKind.priscillaInt8.dirName, 'priscilla-int8');
  });

  test('aquilaInt8 pack kind has the expected format and directory name', () {
    expect(PackKind.aquilaInt8.format, 'aquila-int8-v1');
    expect(PackKind.aquilaInt8.dirName, 'aquila-int8');
  });

  group('PackStore.adoptVerified', () {
    late Directory tmp;
    late Directory staged;
    late Directory root;

    setUp(() {
      tmp = Directory.systemTemp.createTempSync('adopt_verified_test_');
      staged = Directory('${tmp.path}/staged')..createSync();
      root = Directory('${tmp.path}/root')..createSync();
    });

    tearDown(() {
      tmp.deleteSync(recursive: true);
    });

    test('a real manifest-listed file that happens to end in .ok survives adoption', () async {
      // Apollos's real pack ships a genuine content file named converted.ok (unrelated to the
      // downloader's own .ok resume markers) -- the manifest's own name for it, confirmed from the
      // real shipped zip's manifest.json.
      File('${staged.path}/converted.ok').writeAsStringSync('ok\n');
      File('${staged.path}/manifest.json').writeAsStringSync(jsonEncode({
        'format': 'apollos-int8-v1',
        'files': {
          'converted.ok': {'bytes': 3, 'sha256': 'unused'},
        },
      }));

      final store = PackStore(root, PackKind.apollosInt8);
      final installed = await store.adoptVerified(staged);

      expect(installed.has('converted.ok'), isTrue, reason: 'a manifest-listed .ok file must not be swept up by the downloader-bookkeeping cleanup');
      expect(store.active(), isNotNull);
    });

    test('a genuine leftover downloader marker (not in the manifest) is still cleaned up', () async {
      File('${staged.path}/manifest.json').writeAsStringSync(jsonEncode({
        'format': 'apollos-int8-v1',
        'files': <String, dynamic>{},
      }));
      File('${staged.path}/some-archive.zip.ok').writeAsStringSync('leftover');
      File('${staged.path}/some-archive.zip.part').writeAsStringSync('leftover');

      final store = PackStore(root, PackKind.apollosInt8);
      await store.adoptVerified(staged);

      expect(File('${root.path}/apollos-int8/some-archive.zip.ok').existsSync(), isFalse);
      expect(File('${root.path}/apollos-int8/some-archive.zip.part').existsSync(), isFalse);
    });
  });
}
