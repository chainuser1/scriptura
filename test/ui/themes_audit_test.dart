// Visual audit of every app theme on each section, with real scripture text and the app's own typefaces.
// Renders to local-benchmarks/ui-audit/theme-*.png (gitignored); fails on any layout exception. Skipped without the release.
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app/nav_state.dart';
import 'package:scriptures_reader_mobile/app/theme.dart';
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
  final byFamily = <String, List<String>>{};
  for (final f in Directory('assets/fonts').listSync().whereType<File>().where((f) => f.path.endsWith('.ttf'))) {
    final name = f.uri.pathSegments.last;
    final family = switch (name.split('-').first) { 'SourceSerif4' => 'ScriptureSerif', final n => n };
    (byFamily[family] ??= []).add(f.path);
  }
  for (final e in byFamily.entries) {
    final l = FontLoader(e.key);
    for (final p in e.value) {
      l.addFont(Future.value(ByteData.view(File(p).readAsBytesSync().buffer)));
    }
    await l.load();
  }
  await (FontLoader('MaterialIcons')..addFont(Future.value(ByteData.view(File('$fonts/materialicons-regular.otf').readAsBytesSync().buffer)))).load();
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

  group('themes visual audit', skip: ready ? false : 'release not built', () {
    late ContentRepository repo;
    setUpAll(() async {
      await _loadFonts();
      final db = ContentDatabase.open('${release.path}/content.db');
      repo = ContentRepository(db, Catalog.load('${release.path}/catalog.db', contract: db.contract));
    });

    for (final size in const [Size(412, 900), Size(1366, 768)]) {
      final tag = '${size.width.toInt()}x${size.height.toInt()}';
      testWidgets('every theme on every section at $tag', (tester) async {
        tester.view.physicalSize = size;
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.reset);
        final user = UserStore.memory();
        final a32 = verseIdOf(repo, 'Alma', 32, 21)!;
        final app = AppController.fixed(repository: repo, search: FakeSearchService((r, i) async => semantic([a32, a32 + 1, a32 + 2])), user: user);
        await tester.pumpWidget(RepaintBoundary(key: _shot, child: ScripturesReaderApp(app: app)));
        await tester.pumpAndSettle();
        app.nav.openChapter(repo.catalog.chapterOfVerse(a32)!.bookId, 32, verseNumber: 21);
        await tester.pumpAndSettle();
        for (final style in AppStyle.values) {
          user.setPref('app_theme', style.name);
          for (final d in Dest.values) {
            app.nav.go(d);
            await tester.pumpAndSettle();
            await tester.pump(const Duration(seconds: 1));
            await _snap(tester, 'theme-${style.name}-${d.name}-$tag');
            expect(tester.takeException(), isNull, reason: '${style.name} ${d.name} at $tag');
          }
        }
      });
    }
  });
}
