// Layout audit at real desktop window sizes with real scripture text and real fonts. Renders each screen to
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
import 'package:scriptures_reader_mobile/data/user/user_store.dart';
import 'package:scriptures_reader_mobile/main.dart';
import 'package:scriptures_reader_mobile/services/engine/search_models.dart';

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

  group('desktop layout audit', skip: ready ? false : 'release not built', () {
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
      user.toggleHighlight(a32 - 1, 0);
      user.toggleHighlight(a32 + 1, 2);
      user.addNote(a32, 'Faith is hope for things not seen — compare Hebrews 11:1.');
      user.savePosition(repo.catalog.chapterOfVerse(a32)!.bookId, 32, 21);
      final svc = FakeSearchService((r, id) async {
        final ids = [for (final v in const [('Hebrews', 11, 1), ('Alma', 32, 21), ('Ether', 12, 6), ('Romans', 10, 17), ('James', 2, 17), ('Moroni', 7, 41)]) verseIdOf(repo, v.$1, v.$2, v.$3)!];
        return semantic(ids,
            person: r.query == 'Who is Moroni?'
                ? PersonInterpretation('ambiguous', [
                    PersonChip('a', 'Moroni', 'Captain Moroni, chief captain of the Nephite armies', false),
                    PersonChip('b', 'Moroni', 'son of Mormon, last Nephite prophet', false),
                  ], false)
                : null);
      });
      final app = AppController.fixed(repository: repo, search: svc, user: user);
      await tester.pumpWidget(RepaintBoundary(key: _shot, child: ScripturesReaderApp(app: app)));
      await tester.pumpAndSettle();
      return app;
    }

    for (final size in const [Size(1366, 768), Size(1000, 640), Size(480, 700)]) {
      final tag = '${size.width.toInt()}x${size.height.toInt()}';

      testWidgets('home, reading and settings at $tag', (tester) async {
        final app = await boot(tester, size);
        await _snap(tester, 'home-$tag');
        expect(tester.takeException(), isNull);

        app.nav.openChapter(repo.catalog.chapterOfVerse(verseIdOf(repo, 'Alma', 32, 21)!)!.bookId, 32, verseNumber: 21);
        await tester.pumpAndSettle();
        await tester.pump(const Duration(seconds: 1)); // the floating chapter buttons settle after the scroll
        await tester.pump(const Duration(milliseconds: 400));
        await _snap(tester, 'read-$tag');
        expect(tester.takeException(), isNull);

        app.user.setPref('parallel', 'spanish');
        await tester.pumpAndSettle();
        await _snap(tester, 'read-parallel-$tag');
        expect(tester.takeException(), isNull);
        app.user.setPref('parallel', '');

        app.nav.go(Dest.settings);
        await tester.pumpAndSettle();
        await _snap(tester, 'settings-$tag');
        expect(tester.takeException(), isNull);
      });

      testWidgets('search and study at $tag', (tester) async {
        final app = await boot(tester, size);
        app.nav.go(Dest.search);
        await tester.pumpAndSettle();
        await _snap(tester, 'search-empty-$tag');
        await tester.enterText(find.byType(TextField).first, 'Who is Moroni?');
        await tester.testTextInput.receiveAction(TextInputAction.search);
        await tester.pumpAndSettle();
        await _snap(tester, 'search-results-$tag');
        expect(tester.takeException(), isNull);

        app.nav.go(Dest.study);
        await tester.pumpAndSettle();
        await _snap(tester, 'study-$tag');
        expect(tester.takeException(), isNull);
      });
    }
  });
}
