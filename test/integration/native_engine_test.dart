// Real native engine through FFI and the worker isolate: offline, no network. Skipped when the built DLL or the
// generated packs are absent (they are large and gitignored).
//
//   flutter test test/integration/native_engine_test.dart
@Timeout(Duration(minutes: 5))
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/services/engine/engine_pack.dart';
import 'package:scriptures_reader_mobile/services/engine/search_models.dart';
import 'package:scriptures_reader_mobile/services/engine/search_service.dart';

InstalledPack? _pack(String dir) {
  final m = File('$dir/manifest.json');
  return m.existsSync() ? InstalledPack(Directory(dir), jsonDecode(m.readAsStringSync()) as Map<String, dynamic>) : null;
}

void main() {
  final lib = EnginePaths.findLibrary();
  final engine = _pack('generated-artifacts/engine-pack');
  final colbert = _pack('generated-artifacts/colbert-pack-v1');
  final release = Directory('generated-artifacts/release');
  final ready = lib != null && engine != null && release.existsSync();

  group('native engine', skip: ready ? false : 'engine library or packs not built', () {
    late NativeSearchService svc;

    setUpAll(() async {
      final paths = EnginePaths(
        libraryPath: lib!,
        engine: engine!,
        colbert: colbert,
        phraseDb: '${release.path}/phrase-index.db',
        catalogDb: '${release.path}/catalog.db',
      );
      svc = await NativeSearchService.open(libraryPath: lib, config: paths.config());
    });
    tearDownAll(() async => svc.close());

    test('semantic search returns ranked verse IDs with a configuration identity', () async {
      final r = await svc.search(SearchRequest.semantic('What is faith?'));
      expect(r.mode, 'semantic');
      expect(r.hits, hasLength(20));
      expect(r.hits.first.score, greaterThanOrEqualTo(r.hits.last.score));
      expect(r.configurationId, hasLength(64));
      expect(r.profile, 'compass');
    });

    test('a scripture reference is recognised before any semantic work', () async {
      final r = await svc.search(SearchRequest.search('John 3:16'));
      expect(r.mode, 'reference');
      expect(r.reference!.status, 'ok');
      expect(r.reference!.firstVerseId, 26137);
    });

    test('a person question carries an interpretation and the right person', () async {
      final r = await svc.search(SearchRequest.search('Who is Captain Moroni?'));
      expect(r.mode, 'semantic');
      expect(r.person!.status, 'single');
      expect(r.person!.people.first.entityId, 'person:moroni_captain');
    });

    test('phrase search finds the exact passage and reports totals', () async {
      final r = await svc.search(SearchRequest.phrase('the Lord is my shepherd'));
      expect(r.mode, 'phrase');
      expect(r.total, greaterThanOrEqualTo(1));
    });

    test('similar verses never include the source and honour filters', () async {
      final r = await svc.search(SearchRequest.similar(26137, topK: 5, filter: const [VerseRange(26100, 26110)]));
      expect(r.hits, isNotEmpty);
      expect(r.hits.map((h) => h.verseId), isNot(contains(26137)));
      expect(r.hits.every((h) => h.verseId >= 26100 && h.verseId <= 26110), isTrue);
    });

    test('filters restrict semantic results', () async {
      final r = await svc.search(SearchRequest.semantic('faith', topK: 5, filter: const [VerseRange(26137, 26200)]));
      expect(r.hits.every((h) => h.verseId >= 26137 && h.verseId <= 26200), isTrue);
    });

    test('typed failures, never crashes', () async {
      expect(() => svc.search(SearchRequest.semantic('   ')), throwsA(isA<SearchFailure>().having((e) => e.code, 'code', 'invalid_input')));
      expect(() => svc.search(SearchRequest.phrase('faith', language: 'klingon')),
          throwsA(isA<SearchFailure>().having((e) => e.code, 'code', 'unsupported_language')));
      expect(() => svc.search(SearchRequest.similar(-1)), throwsA(isA<SearchFailure>().having((e) => e.code, 'code', 'unknown_verse')));
    });

    test('a cancelled request completes as cancelled and does not block the next one', () async {
      final id = svc.nextRequestId();
      final first = svc.search(SearchRequest.semantic('What does the Bible teach about forgiveness?'), requestId: id);
      svc.cancel(id);
      await expectLater(first, throwsA(isA<SearchFailure>().having((e) => e.cancelled, 'cancelled', isTrue)));
      final next = await svc.search(SearchRequest.semantic('faith'));
      expect(next.hits, isNotEmpty);
    });

    test('works in Spanish and Tagalog queries', () async {
      final es = await svc.search(SearchRequest.search('¿Quién fue el capitán Moroni?'));
      expect(es.person?.people.first.entityId, 'person:moroni_captain');
      final tl = await svc.search(SearchRequest.semantic('Ano ang kapatawaran?'));
      expect(tl.hits, isNotEmpty);
    });
  });
}
