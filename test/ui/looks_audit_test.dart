// Layout audit of every reading look, Settings and the Aa menu, with real scripture text and the app's own typefaces.
// Renders to local-benchmarks/ui-audit/looks-*.png (gitignored); fails on any layout exception. Skipped without the release.
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app/looks.dart';
import 'package:scriptures_reader_mobile/app/nav_state.dart';
import 'package:scriptures_reader_mobile/app/verse_tools.dart';
import 'package:scriptures_reader_mobile/app_controller.dart';
import 'package:scriptures_reader_mobile/data/content/catalog.dart';
import 'package:scriptures_reader_mobile/data/content/content_database.dart';
import 'package:scriptures_reader_mobile/data/content/content_repository.dart';
import 'package:scriptures_reader_mobile/data/user/user_store.dart';
import 'package:scriptures_reader_mobile/main.dart';

import '../fakes/fake_search_service.dart';

final _out = Directory('local-benchmarks/ui-audit')..createSync(recursive: true);
final _shot = GlobalKey();

Future<void> _loadFonts() async {
  final fonts = '${Platform.environment['USERPROFILE']}/develop/flutter/bin/cache/artifacts/material_fonts';
  Future<ByteData> bytes(String f) async => ByteData.view(File('$fonts/$f').readAsBytesSync().buffer);
  Future<void> family(String name, List<String> files) async {
    final l = FontLoader(name);
    for (final f in files) {
      l.addFont(Future.value(ByteData.view(File('assets/fonts/$f').readAsBytesSync().buffer)));
    }
    await l.load();
  }

  await family('Inter', ['Inter-Regular.ttf', 'Inter-Italic.ttf', 'Inter-Medium.ttf', 'Inter-SemiBold.ttf', 'Inter-Bold.ttf']);
  await family('ScriptureSerif', ['SourceSerif4-Regular.ttf', 'SourceSerif4-It.ttf', 'SourceSerif4-Semibold.ttf', 'SourceSerif4-Bold.ttf']);
  await family('Literata', ['Literata-Regular.ttf', 'Literata-Italic.ttf', 'Literata-SemiBold.ttf', 'Literata-Bold.ttf']);
  await family('AtkinsonHyperlegible', ['AtkinsonHyperlegible-Regular.ttf', 'AtkinsonHyperlegible-Italic.ttf', 'AtkinsonHyperlegible-Bold.ttf']);
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

  group('looks layout audit', skip: ready ? false : 'release not built', () {
    late ContentRepository repo;
    setUpAll(() async {
      await _loadFonts();
      final db = ContentDatabase.open('${release.path}/content.db');
      repo = ContentRepository(db, Catalog.load('${release.path}/catalog.db', contract: db.contract));
    });

    Future<AppController> boot(WidgetTester tester, Size size) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final user = UserStore.memory();
      final a32 = verseIdOf(repo, 'Alma', 32, 21)!;
      user.toggleBookmark(a32);
      user.toggleHighlight(a32 + 1, 2);
      final app = AppController.fixed(repository: repo, search: FakeSearchService((r, i) async => semantic([a32])), user: user);
      await tester.pumpWidget(RepaintBoundary(key: _shot, child: ScripturesReaderApp(app: app)));
      await tester.pumpAndSettle();
      app.nav.openChapter(repo.catalog.chapterOfVerse(a32)!.bookId, 32, verseNumber: 21);
      await tester.pumpAndSettle();
      return app;
    }

    for (final size in const [Size(480, 700), Size(1366, 768)]) {
      final tag = '${size.width.toInt()}x${size.height.toInt()}';

      testWidgets('every look in the reader at $tag', (tester) async {
        final app = await boot(tester, size);
        for (final look in looks) {
          applyLook(app.user, look);
          await tester.pumpAndSettle();
          await tester.pump(const Duration(seconds: 1));
          await tester.pump(const Duration(milliseconds: 400));
          await _snap(tester, 'looks-read-${look.id}-$tag');
          expect(tester.takeException(), isNull, reason: '${look.id} at $tag');
        }
      });

      testWidgets('Settings and the Aa menu at $tag', (tester) async {
        final app = await boot(tester, size);
        await tester.tap(find.byTooltip('Reading look, text size and colour'));
        await tester.pumpAndSettle();
        await _snap(tester, 'looks-aa-$tag');
        expect(tester.takeException(), isNull);
        await tester.tap(find.byTooltip('Close'));
        await tester.pumpAndSettle();
        app.nav.go(Dest.settings);
        await tester.pumpAndSettle();
        await _snap(tester, 'looks-settings-$tag');
        await tester.tap(find.text('Fine-tune the look'));
        await tester.pumpAndSettle();
        await _snap(tester, 'looks-settings-fine-$tag');
        expect(tester.takeException(), isNull);
      });
    }
  });
}
