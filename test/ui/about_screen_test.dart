import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app/theme.dart';
import 'package:scriptures_reader_mobile/features/about/about_screen.dart';

void main() {
  for (final size in const [Size(420, 800), Size(1100, 700)]) {
    testWidgets('the story page reads cleanly at ${size.width.toInt()} px', (tester) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(theme: appTheme(Brightness.light), home: const AboutScreen()));
      expect(find.text('The story behind this app'), findsOneWidget);
      expect(find.textContaining('Scripture Genome Project'), findsWidgets);
      expect(find.text('1 · THE GENOME'), findsOneWidget);
      // every section is reachable by scrolling and nothing overflows
      await tester.dragUntilVisible(find.text('CREDITS'), find.byType(ListView), const Offset(0, -300));
      expect(find.textContaining('Jayson Rael Ramos'), findsWidgets);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('guidelines: labelled, tappable targets and contrast', (tester) async {
    final handle = tester.ensureSemantics();
    await tester.pumpWidget(MaterialApp(theme: appTheme(Brightness.light), home: const AboutScreen()));
    await expectLater(tester, meetsGuideline(textContrastGuideline));
    handle.dispose();
  });
}
