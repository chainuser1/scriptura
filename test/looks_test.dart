import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app/looks.dart';
import 'package:scriptures_reader_mobile/app/theme.dart';
import 'package:scriptures_reader_mobile/data/user/user_store.dart';

void main() {
  late UserStore user;
  setUp(() => user = UserStore.memory());
  tearDown(() => user.dispose());

  test('with nothing set the reading preferences are the Book look', () {
    final p = ReadingPrefs.of(user);
    expect(p.theme, ReadingTheme.paper);
    expect(p.font, ReadingFont.sourceSerif);
    expect(p.scale, 1.0);
    expect(p.spacing, LineSpacing.comfortable);
    expect(p.width, 1);
    expect(p.numbers, VerseNumbers.inline);
    expect(p.layout, VerseLayout.flow);
    expect(p.autoNight, isFalse);
    expect(lookOf(user)?.id, 'book');
  });

  test('every look applies completely, and is recognised afterwards', () {
    for (final look in looks) {
      applyLook(user, look);
      expect(lookOf(user)?.id, look.id, reason: look.id);
    }
  });

  test('changing any one control makes the look custom', () {
    applyLook(user, looks.firstWhere((l) => l.id == 'ereader'));
    expect(lookOf(user)?.id, 'ereader');
    user.setPref('text_scale', '1.40');
    expect(lookOf(user), isNull);
  });

  test('every look names a theme, a typeface and a layout that exist', () {
    expect(looks.length, 7);
    expect({for (final l in looks) l.id}.length, looks.length);
    for (final l in looks) {
      final p = ReadingPrefs.resolve(l.values);
      expect(l.values['reading_theme'], p.theme.name, reason: l.id);
      expect(l.values['reading_font'], p.font.name, reason: l.id);
    }
  });

  test('auto night uses the night theme in the evening and early morning only, and keeps a dark theme', () {
    user.setPref('reading_theme', 'sepia');
    user.setPref('auto_night', '1');
    expect(ReadingPrefs.of(user, now: DateTime(2026, 1, 1, 12)).theme, ReadingTheme.sepia);
    expect(ReadingPrefs.of(user, now: DateTime(2026, 1, 1, 21)).theme, ReadingTheme.night);
    expect(ReadingPrefs.of(user, now: DateTime(2026, 1, 1, 5)).theme, ReadingTheme.night);
    user.setPref('reading_theme', 'black');
    expect(ReadingPrefs.of(user, now: DateTime(2026, 1, 1, 22)).theme, ReadingTheme.black, reason: 'already dark');
    user.setPref('auto_night', '0');
    user.setPref('reading_theme', 'paper');
    expect(ReadingPrefs.of(user, now: DateTime(2026, 1, 1, 22)).theme, ReadingTheme.paper);
  });

  test('the scripture style follows the typeface, spacing and size', () {
    user.setPref('reading_font', 'atkinson');
    user.setPref('line_spacing', 'airy');
    user.setPref('text_scale', '1.50');
    final s = ReadingPrefs.of(user).style(color: Colors.black);
    expect(s.fontFamily, 'AtkinsonHyperlegible');
    expect(s.height, 1.9);
    expect(s.fontSize, closeTo(19 * 1.5, 1e-9));
  });

  test('every reading theme keeps a readable contrast between text and page', () {
    double lum(Color c) => c.computeLuminance();
    for (final t in ReadingTheme.values) {
      final a = lum(t.background), b = lum(t.text);
      final ratio = (a > b ? a + 0.05 : b + 0.05) / (a > b ? b + 0.05 : a + 0.05);
      expect(ratio, greaterThanOrEqualTo(7.0), reason: '${t.name} contrast $ratio');
    }
  });
}
