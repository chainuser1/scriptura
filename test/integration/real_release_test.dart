// Verifies the real, locally built release (generated-artifacts/release).
// Skipped automatically when that directory has not been built; it contains no scripture text in the repository.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/data/content/catalog.dart';
import 'package:scriptures_reader_mobile/data/content/content_database.dart';
import 'package:scriptures_reader_mobile/data/content/content_repository.dart';
import 'package:scriptures_reader_mobile/services/artifacts/release_store.dart';

void main() {
  final releaseDir = Directory('generated-artifacts/release');
  final built = File('${releaseDir.path}/content.db').existsSync() && File('${releaseDir.path}/catalog.db').existsSync();

  group('real release', skip: built ? false : 'release directory not built', () {
    late Directory root;
    late ActiveRelease release;
    late ContentDatabase content;
    late ContentRepository repo;
    late Catalog catalog;
    late String contract;

    setUpAll(() async {
      root = Directory.systemTemp.createTempSync('real_release');
      release = await ReleaseStore(root).installFromDirectory(releaseDir, include: requiredReleaseFiles);
      final manifest = jsonDecode(File('${releaseDir.path}/manifest.json').readAsStringSync()) as Map<String, dynamic>;
      contract = (manifest['content_contract'] as Map)['verse_order_sha256'] as String;
      content = ContentDatabase.open(release.path('content.db'));
      catalog = Catalog.load(release.path('catalog.db'), contract: contract);
      repo = ContentRepository(content, catalog);
    });

    tearDownAll(() {
      content.dispose();
      root.deleteSync(recursive: true);
    });

    test('install is verified, active, and the contract matches the manifest', () {
      expect(release.id, 'application-v1+kjv');
      expect(ReleaseStore(root).active()!.id, 'application-v1+kjv');
      expect(content.contract, contract);
      expect(catalog.contract, contract);
    });

    test('only complete languages are served', () {
      expect(repo.servedLanguages, ['cebuano', 'english', 'greek', 'spanish', 'tagalog']);
      for (final l in ['french', 'german', 'hebrew', 'japanese', 'ilocano', 'waray']) {
        expect(() => repo.getPassage(1, language: l), throwsA(isA<ContentException>()), reason: l);
      }
    });

    test('87 books, 41,995 verses, 5 volumes, canonical order', () {
      final books = repo.listBooks();
      expect(books.length, 87);
      expect(books.first.name, 'Genesis');
      expect(books.last.name, 'Articles of Faith');
      expect(books.fold<int>(0, (s, b) => s + b.verses), 41995);
      expect(repo.volumes().length, 5);
    });

    test('English text is KJV or standard-works text; no other source exists', () {
      final gen = repo.getPassage(1);
      expect(gen.text, startsWith('In the beginning God created the heaven'));
      expect(gen.source, 'kjv');
      expect(gen.reference, 'Genesis 1:1');
      final dc = repo.getPassage(39194);
      expect(dc.reference, 'Doctrine and Covenants 64:7');
      expect(dc.source, 'lds');
      final sources = content.db
          .select("SELECT DISTINCT source FROM text_provenance WHERE language = 'english'")
          .map((r) => r['source'])
          .toSet();
      expect(sources, {'kjv', 'lds'});
    });

    test('every served language has exactly 41,995 rows', () {
      for (final l in repo.servedLanguages) {
        final n = content.db.select('SELECT count(*) AS n FROM ${supportedLanguages[l]}').first['n'];
        expect(n, 41995, reason: l);
      }
    });

    test('a served non-English chapter is complete with no fallback and a localized title', () {
      final psalms = repo.resolveBook('Psalms')!;
      final ps = repo.getChapter(psalms.id, 23, language: 'tagalog');
      expect(ps.length, 6);
      expect(ps.every((p) => !p.isFallback), isTrue);
      final first = ps.first.reference;
      expect(first.endsWith(' 23:1'), isTrue, reason: first);
    });

    test('catalog agrees with the content database and names are localized', () {
      expect(catalog.languages, ['english', 'spanish', 'tagalog', 'cebuano', 'greek']);
      expect(repo.listBooks(language: 'spanish').first.name, 'Génesis');
      expect(repo.volumes(language: 'spanish').first.name, 'Antiguo Testamento');
      expect(repo.volumes(language: 'cebuano')[1].name, 'Bag-ong Tugon');
      expect(catalog.bookOfVerse(1)!.canonicalName, 'Genesis');
      expect(catalog.bookOfVerse(41995)!.canonicalName, 'Articles of Faith');
      // the verse count of every chapter equals the number of text rows in its range
      for (final b in repo.listBooks()) {
        final n = content.db
            .select('SELECT count(*) AS n FROM text_english WHERE verse_id BETWEEN ? AND ?', [b.firstVerseId, b.firstVerseId + b.verses - 1])
            .first['n'];
        expect(n, b.verses, reason: b.canonicalName);
      }
    });

    test('references resolve across languages, including known renames', () {
      expect(repo.resolveBook('Salmos', language: 'spanish')!.canonicalName, 'Psalms');
      expect(repo.resolveBook('Song of Solomon')!.canonicalName, 'Song of Songs');
      expect(repo.resolveBook('D&C')!.canonicalName, 'Doctrine and Covenants');
      expect(repo.resolveBook('1 Jn')!.canonicalName, '1 John');
      expect(repo.resolveBook('Juan', language: 'tagalog')!.canonicalName, 'John');
    });

    test('a catalog for another verse-id layout is refused', () {
      expect(() => Catalog.load(release.path('catalog.db'), contract: 'not-the-contract'), throwsA(isA<ContentException>()));
    });
  });
}
