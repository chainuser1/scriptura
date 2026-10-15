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
      expect(find.text('Our story'), findsOneWidget);
      // every section is reachable by scrolling and nothing overflows
      await tester.scrollUntilVisible(find.textContaining('Founder and designer: Jayson Rael Ramos'), 300, scrollable: find.byType(Scrollable).first);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('the story is told for readers: no technical terms', (tester) async {
    tester.view.physicalSize = const Size(1100, 4000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(theme: appTheme(Brightness.light), home: const AboutScreen()));
    for (final heading in ['WORDS ARE NOT THE WHOLE STORY', 'THE SCRIPTURE GENOME PROJECT', 'FROM RESEARCH TO A READER', 'HOW WE MADE IT']) {
      expect(find.text(heading), findsOneWidget, reason: heading);
    }
    expect(find.textContaining('powered by the Scripture Genome Project'), findsOneWidget);
    expect(find.text('A NOTE FROM THE FOUNDER'), findsOneWidget);
    expect(find.textContaining('scriptura.space'), findsWidgets);
    expect(find.textContaining('no one should have to know the right words'), findsOneWidget);
    for (final word in ['language model', 'encoder', 'Rust', 'engine', '568', 'genes', 'embedding', 'schema']) {
      expect(find.textContaining(word), findsNothing, reason: word);
    }
  });

  testWidgets('guidelines: labelled, tappable targets and contrast', (tester) async {
    final handle = tester.ensureSemantics();
    await tester.pumpWidget(MaterialApp(theme: appTheme(Brightness.light), home: const AboutScreen()));
    await expectLater(tester, meetsGuideline(textContrastGuideline));
    handle.dispose();
  });
}
