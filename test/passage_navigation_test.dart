import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app/passage_navigation.dart';
import 'package:scriptures_reader_mobile/app/passage_colors.dart';
import 'package:scriptures_reader_mobile/app/passage_selection.dart';
import 'package:scriptures_reader_mobile/app/theme.dart';

import 'result_groups_test.dart' show verse;

double contrast(Color a, Color b) {
  final luminances = [a.computeLuminance(), b.computeLuminance()]..sort();
  return (luminances.last + 0.05) / (luminances.first + 0.05);
}

void main() {
  test('theme accent selection stays readable on every reading surface', () {
    for (final style in AppStyle.values) {
      for (final brightness in Brightness.values) {
        final scheme = schemeFor(style, brightness);
        for (final reading in ReadingTheme.values) {
          final colors = PassageColors(scheme,
              surface: reading.background, text: reading.text);
          final reason = '${style.name}/${brightness.name}/${reading.name}';
          expect(colors.accent, scheme.primary, reason: reason);
          expect(contrast(colors.onAccent, colors.accent),
              greaterThanOrEqualTo(4.5),
              reason: reason);
          expect(contrast(colors.marker, reading.background),
              greaterThanOrEqualTo(3),
              reason: reason);
          expect(contrast(reading.text, colors.activeFill),
              greaterThanOrEqualTo(4.5),
              reason: reason);
          expect(contrast(reading.text, colors.matchFill),
              greaterThanOrEqualTo(4.5),
              reason: reason);
        }
      }
    }
  });

  testWidgets(
      'passage chips use the reading surface despite a conflicting app theme',
      (tester) async {
    for (final reading in [ReadingTheme.paper, ReadingTheme.night]) {
      final appTheme = reading.isDark ? ThemeData.light() : ThemeData.dark();
      var selection = PassageSelection([verse(3), verse(7)], anchor: verse(7));
      await tester.pumpWidget(MaterialApp(
        theme: appTheme.copyWith(
            chipTheme: appTheme.chipTheme.copyWith(
          color: WidgetStatePropertyAll(appTheme.colorScheme.surface),
        )),
        home: Scaffold(
            body: StatefulBuilder(
          builder: (context, setState) => PassageNavigation(
            selection: selection,
            color: reading.text,
            surfaceColor: reading.background,
            onSelect: (index) =>
                setState(() => selection = selection.atRun(index)),
          ),
        )),
      ));
      await tester.pumpAndSettle();
      final chips =
          tester.widgetList<ChoiceChip>(find.byType(ChoiceChip)).toList();
      expect(chips.map((c) => c.selected), [false, true]);
      for (final chip in chips) {
        final states = chip.selected ? {WidgetState.selected} : <WidgetState>{};
        final fill = chip.color!.resolve(states)!;
        final ink = chip.labelStyle!.color!;
        final luminances = [fill.computeLuminance(), ink.computeLuminance()]
          ..sort();
        expect(fill.a, 1);
        if (chip.selected) expect(fill, appTheme.colorScheme.primary);
        expect((luminances.last + 0.05) / (luminances.first + 0.05),
            greaterThanOrEqualTo(4.5));
        expect(chip.checkmarkColor, ink);
        expect(chip.showCheckmark, isTrue);
      }
      await tester.tap(find.text('3'));
      await tester.pumpAndSettle();
      expect(
          tester
              .widgetList<ChoiceChip>(find.byType(ChoiceChip))
              .map((c) => c.selected),
          [true, false]);
    }
  });
}
