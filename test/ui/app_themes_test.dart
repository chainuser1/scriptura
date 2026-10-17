import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app/brand.dart';
import 'package:scriptures_reader_mobile/app/nav_state.dart';
import 'package:scriptures_reader_mobile/app/theme.dart';
import 'package:scriptures_reader_mobile/app_controller.dart';
import 'package:scriptures_reader_mobile/data/user/user_store.dart';
import 'package:scriptures_reader_mobile/features/settings/reading_controls.dart';
import 'package:scriptures_reader_mobile/main.dart';

import '../fakes/fake_search_service.dart';
import '../widget_test.dart' show fixtureRepository;

double _contrast(Color a, Color b) {
  final x = a.computeLuminance(), y = b.computeLuminance();
  return (x > y ? x + 0.05 : y + 0.05) / (x > y ? y + 0.05 : x + 0.05);
}

/// Everything a person can read or press on screen: text, icons, tooltips and the kinds of controls.
List<String> _inventory(WidgetTester tester) {
  final out = <String>[];
  // The theme picker names the chosen theme; everything else must be identical.
  final picker = find.descendant(of: find.byType(AppThemeGallery), matching: find.byWidgetPredicate((_) => true)).evaluate().toSet();
  for (final e in find.byWidgetPredicate((_) => true).evaluate().where((e) => !picker.contains(e))) {
    final w = e.widget;
    if (w is Text) out.add('text:${w.data ?? w.textSpan?.toPlainText()}');
    if (w is Icon) out.add('icon:${w.icon?.codePoint}');
    if (w is Tooltip) out.add('tip:${w.message}');
    if (w is ScripturesMark) out.add('mark');
    if (w is ButtonStyleButton || w is IconButton || w is TextField || w is Switch || w is Slider || w is Checkbox || w is InkWell) {
      out.add('control:${w.runtimeType}');
    }
  }
  return out..sort();
}

void main() {
  test('Scriptura keeps today\'s look', () {
    final light = appTheme(Brightness.light);
    expect(light.colorScheme.primary, Brand.pink);
    expect(light.colorScheme.surface, Brand.page);
    expect(light.textTheme.bodyMedium?.fontFamily, 'Inter');
    expect(appTheme(Brightness.dark).colorScheme.surface, Brand.navy);
    expect(AppStyle.parse(null), AppStyle.scriptura);
    expect(AppStyle.parse('nonsense'), AppStyle.scriptura);
    expect(AppStyle.scriptura.mode, ThemeMode.system);
  });

  test('every theme keeps text readable in light and dark', () {
    for (final style in AppStyle.values) {
      for (final b in Brightness.values) {
        final s = schemeFor(style, b);
        final at = '${style.name}/${b.name}';
        expect(_contrast(s.onSurface, s.surface), greaterThanOrEqualTo(7.0), reason: '$at text');
        expect(_contrast(s.onSurfaceVariant, s.surface), greaterThanOrEqualTo(4.5), reason: '$at secondary text');
        expect(_contrast(s.primary, s.surface), greaterThanOrEqualTo(3.0), reason: '$at accent');
        expect(_contrast(s.onPrimary, s.primary), greaterThanOrEqualTo(4.5), reason: '$at button text');
        expect(_contrast(s.onPrimaryContainer, s.primaryContainer), greaterThanOrEqualTo(4.5), reason: '$at chip text');
        expect(_contrast(s.onSurface, s.surfaceContainerHighest), greaterThanOrEqualTo(4.5), reason: '$at raised text');
      }
    }
  });

  for (final size in const [Size(1280, 800), Size(400, 860)]) {
    testWidgets('every theme shows the same words, icons and controls on every screen (${size.width.toInt()} wide)', (tester) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final user = UserStore.memory();
      final app = AppController.fixed(repository: fixtureRepository(), search: FakeSearchService((r, i) async => semantic([1])), user: user);
      await tester.pumpWidget(ScripturesReaderApp(app: app));
      await tester.pumpAndSettle();

      Future<Map<Dest, List<String>>> screens() async {
        final out = <Dest, List<String>>{};
        for (final d in Dest.values) {
          app.nav.go(d);
          await tester.pumpAndSettle();
          out[d] = _inventory(tester);
        }
        return out;
      }

      await screens(); // every section once, so each is built before comparing
      final baseline = await screens();
      for (final style in AppStyle.values.skip(1)) {
        user.setPref('app_theme', style.name);
        await tester.pumpAndSettle();
        final ctx = tester.element(find.byType(Scaffold).first);
        expect(Theme.of(ctx).colorScheme, schemeFor(style, style.mode == ThemeMode.dark ? Brightness.dark : Brightness.light), reason: style.name);
        final now = await screens();
        for (final d in Dest.values) {
          expect(now[d], baseline[d], reason: '${style.name} changed what ${d.name} shows');
        }
        expect(tester.takeException(), isNull);
      }
    });
  }

  testWidgets('choosing a theme in Settings applies it to the whole app and is remembered', (tester) async {
    tester.view.physicalSize = const Size(1280, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final user = UserStore.memory();
    final app = AppController.fixed(repository: fixtureRepository(), user: user);
    await tester.pumpWidget(ScripturesReaderApp(app: app));
    await tester.pumpAndSettle();
    app.nav.go(Dest.settings);
    await tester.pumpAndSettle();
    final elegant = find.bySemanticsLabel(RegExp('^Elegant theme'));
    await tester.ensureVisible(elegant);
    await tester.pumpAndSettle();
    await tester.tap(elegant);
    await tester.pumpAndSettle();
    expect(user.pref('app_theme'), 'elegant');
    final ctx = tester.element(find.byType(Scaffold).first);
    expect(Theme.of(ctx).colorScheme.surface, schemeFor(AppStyle.elegant, Brightness.dark).surface);
    expect(Theme.of(ctx).brightness, Brightness.dark);
    expect(find.byType(ScripturesMark), findsWidgets); // the logo stays, in its on-dark colours
    expect(tester.widget<ScripturesMark>(find.byType(ScripturesMark).first).onDark, isTrue);
  });
}
