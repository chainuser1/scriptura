// Layout audit of the Trails screens at real desktop and phone sizes, with real scripture text and fonts. Renders to
// local-benchmarks/ui-audit/*.png (gitignored) and fails on any Flutter layout exception (overflow etc.).
// Skipped when the generated release is absent.
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app/nav_state.dart';
import 'package:scriptures_reader_mobile/app/verse_tools.dart';
import 'package:scriptures_reader_mobile/app_controller.dart';
import 'package:scriptures_reader_mobile/data/content/catalog.dart';
import 'package:scriptures_reader_mobile/data/content/content_database.dart';
import 'package:scriptures_reader_mobile/data/content/content_repository.dart';
import 'package:scriptures_reader_mobile/data/trails/trail_models.dart';
import 'package:scriptures_reader_mobile/data/user/user_store.dart';
import 'package:scriptures_reader_mobile/main.dart';
import 'package:scriptures_reader_mobile/services/engine/search_models.dart';
import 'package:scriptures_reader_mobile/services/engine/search_service.dart';

import '../fakes/fake_search_service.dart';

final _out = Directory('local-benchmarks/ui-audit')..createSync(recursive: true);
final _shot = GlobalKey();

Future<void> _loadFonts() async {
  final fonts = '${Platform.environment['USERPROFILE']}/develop/flutter/bin/cache/artifacts/material_fonts';
  Future<ByteData> bytes(String f) async => ByteData.view(File('$fonts/$f').readAsBytesSync().buffer);
  // The app's own faces, straight from assets/fonts, so the audit images show the real typography.
  Future<void> family(String name, List<String> files) async {
    final l = FontLoader(name);
    for (final f in files) {
      l.addFont(Future.value(ByteData.view(File('assets/fonts/$f').readAsBytesSync().buffer)));
    }
    await l.load();
  }

  await family('Inter', ['Inter-Regular.ttf', 'Inter-Italic.ttf', 'Inter-Medium.ttf', 'Inter-SemiBold.ttf', 'Inter-Bold.ttf']);
  await family('ScriptureSerif', ['SourceSerif4-Regular.ttf', 'SourceSerif4-It.ttf', 'SourceSerif4-Semibold.ttf', 'SourceSerif4-Bold.ttf']);
  final icons = FontLoader('MaterialIcons')..addFont(bytes('materialicons-regular.otf'));
  await icons.load();
}

Future<void> _snap(WidgetTester tester, String name) async {
  await tester.runAsync(() async {
    final boundary = _shot.currentContext!.findRenderObject() as RenderRepaintBoundary;
    final image = await boundary.toImage(pixelRatio: 1);
    final data = await image.toByteData(format: ui.ImageByteFormat.png);
    File('${_out.path}/$name.png').writeAsBytesSync(data!.buffer.asUint8List());
  });
}

void main() {
  final release = Directory('generated-artifacts/release');
  final ready = release.existsSync() && Directory('${Platform.environment['USERPROFILE']}/develop/flutter').existsSync();

  group('trails layout audit', skip: ready ? false : 'release not built', () {
    late ContentRepository repo;
    late List<int> verses;

    setUpAll(() async {
      await _loadFonts();
      final db = ContentDatabase.open('${release.path}/content.db');
      repo = ContentRepository(db, Catalog.load('${release.path}/catalog.db', contract: db.contract));
      verses = [
        for (final v in const [('Alma', 32, 21), ('Romans', 8, 28), ('Psalms', 23, 4), ('2 Nephi', 31, 20), ('John', 14, 27), ('Isaiah', 41, 10), ('Mosiah', 2, 17)])
          verseIdOf(repo, v.$1, v.$2, v.$3)!
      ];
    });

    SearchResponse batch(List<int> ids) => SearchResponse.fromJson({
          'mode': 'trail',
          'hits': [
            for (final v in ids) {'verse_id': v, 'score': 1.0, 'parts': {'genome': 1.0, 'topics': 0.0, 'taste': 0.2, 'novelty': 0.1, 'mood': 0.3, 'explore': false}}
          ],
          'family_weights': List<double>.filled(23, 0.0)..[3] = 0.8..[5] = 0.5,
          'leans': ['D', 'F'],
          'widened': 0,
          'candidates': ids.length,
        });

    Future<AppController> boot(WidgetTester tester, Size size, {SearchService? service, bool withMood = true, bool emptyBatches = false}) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final user = UserStore.memory();
      user.toggleBookmark(verses[1]);
      var cursor = 0;
      final svc = FakeSearchService((r, id) async {
        switch (r.op) {
          case 'explain':
            return SearchResponse.fromJson({
              'mode': 'explain',
              'families': [
                {'family': 'D', 'share': 0.34, 'genes': [{'id': 'D18_emotion_comfort_consolation', 'a': 0.2, 'b': 0.3}, {'id': 'D08_emotion_peace_stillness', 'a': 0.1, 'b': 0.2}]},
                {'family': 'F', 'share': 0.21, 'genes': [{'id': 'F09_divine_love_mercy', 'a': 0.2, 'b': 0.2}]},
              ],
              'mood_matches': ['D18_emotion_comfort_consolation'],
              'shared_terms': ['believeth', 'everlasting'],
              'shared_entities': [{'id': 'person:christ', 'name': 'Jesus Christ'}],
            });
          case 'taste':
            return SearchResponse.fromJson({
              'mode': 'taste',
              'families': [{'family': 'D', 'score': 0.9}, {'family': 'F', 'score': 0.6}, {'family': 'S', 'score': 0.3}]
            });
          default:
            return emptyBatches ? batch(const []) : batch([for (var i = 0; i < 5; i++) verses[(cursor++) % verses.length]]);
        }
      });
      final app = AppController.fixed(repository: repo, search: service ?? svc, user: user);
      final t = user.createTrail(
        name: withMood ? 'Finding comfort' : 'From Alma 32:21',
        seed: withMood ? const TrailSeed.question('Where can I find comfort when I grieve?') : TrailSeed.verse(verses[0]),
        moods: withMood ? ['comfort'] : const [],
      );
      user.addTrailEvent(t.id, verses[0], TrailAction.shown);
      user.addTrailEvent(t.id, verses[0], TrailAction.like);
      user.addTrailEvent(t.id, verses[1], TrailAction.shown);
      user.addTrailEvent(t.id, verses[1], TrailAction.like);
      user.addTrailEvent(t.id, verses[2], TrailAction.shown);
      if (emptyBatches) user.addTrailEvent(t.id, verses[2], TrailAction.skip); // so the trail asks the engine for more
      user.setPref('active_trail', t.id);
      await tester.pumpWidget(RepaintBoundary(key: _shot, child: ScripturesReaderApp(app: app)));
      await tester.pumpAndSettle();
      return app;
    }

    for (final size in const [Size(1366, 768), Size(1000, 640), Size(480, 700)]) {
      final tag = '${size.width.toInt()}x${size.height.toInt()}';

      testWidgets('home, trail, sheets, return bar, study and taste at $tag', (tester) async {
        final app = await boot(tester, size);
        await _snap(tester, 'home-starters-$tag');
        expect(tester.takeException(), isNull);

        await tester.tap(find.text('Resume'));
        await tester.pumpAndSettle();
        await _snap(tester, 'trail-card-mood-$tag');
        expect(tester.takeException(), isNull);

        await tester.tap(find.text('Why this verse'));
        await tester.pumpAndSettle();
        await _snap(tester, 'trail-why-$tag');
        expect(tester.takeException(), isNull);
        await tester.tap(find.byTooltip('Close'));
        await tester.pumpAndSettle();

        await tester.tap(find.byIcon(Icons.tune));
        await tester.pumpAndSettle();
        await _snap(tester, 'trail-tune-$tag');
        expect(tester.takeException(), isNull);
        await tester.tapAt(const Offset(4, 4));
        await tester.pumpAndSettle();

        await tester.tap(find.byTooltip('Back'));
        await tester.pumpAndSettle();
        app.nav.openChapter(repo.catalog.chapterOfVerse(verses[0])!.bookId, 32, verseNumber: 21);
        await tester.pumpAndSettle();
        await _snap(tester, 'return-bar-read-$tag');
        app.nav.go(Dest.settings);
        await tester.pumpAndSettle();
        await _snap(tester, 'return-bar-settings-$tag');
        expect(tester.takeException(), isNull);

        app.nav.go(Dest.study);
        await tester.pumpAndSettle();
        await tester.ensureVisible(find.text('Trails'));
        await tester.pumpAndSettle();
        await tester.tap(find.text('Trails'));
        await tester.pumpAndSettle();
        await _snap(tester, 'study-trails-$tag');
        await tester.tap(find.text('Your reading taste'));
        await tester.pumpAndSettle();
        await _snap(tester, 'taste-$tag');
        expect(tester.takeException(), isNull);
      });

      testWidgets('a plain card at $tag', (tester) async {
        await boot(tester, size, withMood: false);
        await tester.tap(find.text('Resume'));
        await tester.pumpAndSettle();
        await _snap(tester, 'trail-card-$tag');
        expect(tester.takeException(), isNull);
      });

      testWidgets('the empty trail at $tag', (tester) async {
        await boot(tester, size, emptyBatches: true);
        await tester.tap(find.text('Resume'));
        await tester.pumpAndSettle();
        await _snap(tester, 'trail-empty-$tag');
        expect(tester.takeException(), isNull);
      });

      testWidgets('the missing-data state at $tag', (tester) async {
        await boot(tester, size, service: UnavailableSearchService('Search data is not installed. It downloads by itself on first run.'));
        await tester.tap(find.text('Resume'));
        await tester.pumpAndSettle();
        await _snap(tester, 'trail-engine-down-$tag');
        expect(tester.takeException(), isNull);
      });
    }
  });
}
