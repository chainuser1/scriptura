import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app/passage_navigation.dart';
import 'package:scriptures_reader_mobile/app/passage_selection.dart';
import 'package:scriptures_reader_mobile/app/theme.dart';

import 'result_groups_test.dart' show verse;

void main() {
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
