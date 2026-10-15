import 'package:flutter/material.dart';

import '../data/user/user_store.dart';
import 'theme.dart';

/// How scripture is set: colours, typeface, size, spacing, line width, verse numbers and layout. The individual controls
/// are stored as preferences; a "look" is a named bundle of them. Nothing here changes what a verse says.

enum ReadingFont {
  sourceSerif('Source Serif', 'ScriptureSerif', ['Georgia', 'Cambria', 'Times New Roman', 'serif']),
  literata('Literata', 'Literata', ['Georgia', 'Cambria', 'serif']),
  inter('Inter', 'Inter', ['Segoe UI', 'Roboto', 'sans-serif']),
  atkinson('Atkinson Hyperlegible', 'AtkinsonHyperlegible', ['Segoe UI', 'Roboto', 'sans-serif']);

  const ReadingFont(this.label, this.family, this.fallback);
  final String label, family;
  final List<String> fallback;

  static ReadingFont parse(String? s) => values.firstWhere((f) => f.name == s, orElse: () => ReadingFont.sourceSerif);
}

enum LineSpacing {
  compact('Compact', 1.45),
  comfortable('Comfortable', 1.65),
  airy('Airy', 1.9);

  const LineSpacing(this.label, this.height);
  final String label;
  final double height;

  static LineSpacing parse(String? s) => values.firstWhere((f) => f.name == s, orElse: () => LineSpacing.comfortable);
}

enum VerseNumbers {
  inline('Inline'),
  margin('In the margin'),
  hidden('Hidden');

  const VerseNumbers(this.label);
  final String label;

  static VerseNumbers parse(String? s) => values.firstWhere((f) => f.name == s, orElse: () => VerseNumbers.inline);
}

enum VerseLayout {
  flow('Flowing text'),
  cards('Cards');

  const VerseLayout(this.label);
  final String label;

  static VerseLayout parse(String? s) => values.firstWhere((f) => f.name == s, orElse: () => VerseLayout.flow);
}

/// Evenings and early mornings, by the clock (no location is ever read).
bool isNightHour(DateTime t) => t.hour >= 19 || t.hour < 6;

class ReadingPrefs {
  const ReadingPrefs({
    required this.theme,
    required this.font,
    required this.scale,
    required this.spacing,
    required this.width,
    required this.numbers,
    required this.layout,
    required this.autoNight,
  });

  final ReadingTheme theme;
  final ReadingFont font;
  final double scale;
  final LineSpacing spacing;

  /// 0 narrow, 1 medium, 2 wide.
  final int width;
  final VerseNumbers numbers;
  final VerseLayout layout;
  final bool autoNight;

  /// The preferences stored for [user]. With auto night on, the evening hours use a dark theme.
  factory ReadingPrefs.of(UserStore user, {DateTime? now}) {
    final p = ReadingPrefs.resolve({
      for (final k in _keys) k: user.pref(k) ?? '',
    });
    if (p.autoNight && !p.theme.isDark && isNightHour(now ?? DateTime.now())) {
      return ReadingPrefs(
        theme: ReadingTheme.night,
        font: p.font,
        scale: p.scale,
        spacing: p.spacing,
        width: p.width,
        numbers: p.numbers,
        layout: p.layout,
        autoNight: true,
      );
    }
    return p;
  }

  /// From raw preference strings (a look's values, or stored preferences); anything missing takes its default.
  factory ReadingPrefs.resolve(Map<String, String> v) => ReadingPrefs(
        theme: ReadingTheme.parse(v['reading_theme']),
        font: ReadingFont.parse(v['reading_font']),
        scale: (double.tryParse(v['text_scale'] ?? '') ?? 1.0).clamp(0.8, 1.8),
        spacing: LineSpacing.parse(v['line_spacing']),
        width: (int.tryParse(v['reading_width'] ?? '') ?? 1).clamp(0, 2),
        numbers: VerseNumbers.parse(v['verse_numbers']),
        layout: VerseLayout.parse(v['verse_layout']),
        autoNight: v['auto_night'] == '1',
      );

  /// The scripture text style; [extraScale] shrinks it for previews and side panels.
  TextStyle style({required Color color, double extraScale = 1.0}) => TextStyle(
        fontFamily: font.family,
        fontFamilyFallback: font.fallback,
        fontSize: 19 * scale * extraScale,
        height: spacing.height,
        color: color,
      );

  static const _keys = ['reading_theme', 'reading_font', 'text_scale', 'line_spacing', 'reading_width', 'verse_numbers', 'verse_layout', 'auto_night'];
}

/// A named bundle of reading preferences.
class ReadingLook {
  const ReadingLook(this.id, this.name, this.blurb, this.values);
  final String id, name, blurb;
  final Map<String, String> values;
}

const looks = <ReadingLook>[
  ReadingLook('book', 'Book', 'Paper, a classic serif, one calm column.', {
    'reading_theme': 'paper', 'reading_font': 'sourceSerif', 'text_scale': '1.00', 'line_spacing': 'comfortable',
    'reading_width': '1', 'verse_numbers': 'inline', 'verse_layout': 'flow', 'auto_night': '0',
  }),
  ReadingLook('ereader', 'E-reader', 'Warm page, large serif, narrow lines, numbers in the margin.', {
    'reading_theme': 'sepia', 'reading_font': 'literata', 'text_scale': '1.15', 'line_spacing': 'airy',
    'reading_width': '0', 'verse_numbers': 'margin', 'verse_layout': 'flow', 'auto_night': '0',
  }),
  ReadingLook('web', 'Web', 'White page, clean sans, wide lines.', {
    'reading_theme': 'white', 'reading_font': 'inter', 'text_scale': '1.00', 'line_spacing': 'comfortable',
    'reading_width': '2', 'verse_numbers': 'inline', 'verse_layout': 'flow', 'auto_night': '0',
  }),
  ReadingLook('cards', 'App', 'Each verse on its own card, with its menu in reach.', {
    'reading_theme': 'mist', 'reading_font': 'inter', 'text_scale': '1.00', 'line_spacing': 'comfortable',
    'reading_width': '1', 'verse_numbers': 'margin', 'verse_layout': 'cards', 'auto_night': '0',
  }),
  ReadingLook('study', 'Study desk', 'Compact and wide, for working across many verses.', {
    'reading_theme': 'paper', 'reading_font': 'sourceSerif', 'text_scale': '0.90', 'line_spacing': 'compact',
    'reading_width': '2', 'verse_numbers': 'inline', 'verse_layout': 'flow', 'auto_night': '0',
  }),
  ReadingLook('night', 'Night', 'True black, warm text, and it dims the page after dark.', {
    'reading_theme': 'black', 'reading_font': 'literata', 'text_scale': '1.00', 'line_spacing': 'comfortable',
    'reading_width': '1', 'verse_numbers': 'inline', 'verse_layout': 'flow', 'auto_night': '1',
  }),
  ReadingLook('largeprint', 'Large print', 'Big type, high contrast, generous spacing.', {
    'reading_theme': 'contrast', 'reading_font': 'atkinson', 'text_scale': '1.50', 'line_spacing': 'airy',
    'reading_width': '0', 'verse_numbers': 'inline', 'verse_layout': 'flow', 'auto_night': '0',
  }),
];

void applyLook(UserStore user, ReadingLook look) {
  look.values.forEach(user.setPref);
}

/// The look whose values match the stored preferences exactly, or null ("Custom").
ReadingLook? lookOf(UserStore user) {
  final now = ReadingPrefs.of(user, now: DateTime(2000, 1, 1, 12));
  for (final l in looks) {
    final p = ReadingPrefs.resolve(l.values);
    if (p.theme == now.theme &&
        p.font == now.font &&
        (p.scale - now.scale).abs() < 0.005 &&
        p.spacing == now.spacing &&
        p.width == now.width &&
        p.numbers == now.numbers &&
        p.layout == now.layout &&
        p.autoNight == now.autoNight) {
      return l;
    }
  }
  return null;
}
