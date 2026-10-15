import 'package:flutter/material.dart';

import 'brand.dart';

/// The reading surface has its own colours, independent of the window chrome (which follows the system). Every pair keeps
/// a contrast of at least 7:1 (WCAG AAA); looks_test.dart enforces it.
enum ReadingTheme {
  paper('Paper', Color(0xFFFBF8F1), Color(0xFF2A2420)),
  sepia('Sepia', Color(0xFFF1E4C8), Color(0xFF4A3A28)),
  white('Clean', Color(0xFFFFFFFF), Color(0xFF1F1F1F)),
  mist('Mist', Color(0xFFEEF2F6), Color(0xFF1F2933)),
  forest('Forest', Color(0xFFE9F0E4), Color(0xFF22301F)),
  slate('Slate', Color(0xFF2B2F36), Color(0xFFE4E6EA)),
  night('Night', Color(0xFF16181C), Color(0xFFD9D4C7)),
  black('Black', Color(0xFF000000), Color(0xFFC8C3B8)),
  contrast('High contrast', Color(0xFFFFFFFF), Color(0xFF000000));

  const ReadingTheme(this.label, this.background, this.text);
  final String label;
  final Color background, text;

  bool get isDark => background.computeLuminance() < 0.2;

  static ReadingTheme parse(String? s) => values.firstWhere((t) => t.name == s, orElse: () => ReadingTheme.paper);
}

/// Scripture is set in Source Serif 4, bundled with the app (SIL OFL); system serifs are only a fallback.
TextStyle scriptureStyle(BuildContext context, {required double scale, required Color color, String family = 'ScriptureSerif', List<String>? fallback, double height = 1.65}) => TextStyle(
      fontFamily: family,
      fontFamilyFallback: fallback ?? const ['Georgia', 'Cambria', 'Times New Roman', 'serif'],
      fontSize: 19 * scale,
      height: height,
      color: color,
    );

/// Highlight colours as translucent washes that stay readable on all three reading themes.
const highlightPalette = <Color>[
  Color(0x66F2C94C), // gold
  Color(0x667FB77E), // green
  Color(0x6679B4E8), // blue
  Color(0x66E58FA8), // rose
  Color(0x66B79AE0), // violet
];

const highlightNames = ['Gold', 'Green', 'Blue', 'Rose', 'Violet'];

const _lightScheme = ColorScheme(
  brightness: Brightness.light,
  primary: Brand.pink,
  onPrimary: Colors.white,
  primaryContainer: Color(0xFFFBE3EF),
  onPrimaryContainer: Color(0xFF5E0A37),
  secondary: Brand.navy,
  onSecondary: Colors.white,
  secondaryContainer: Color(0xFFE3E6F1),
  onSecondaryContainer: Brand.navy,
  tertiary: Color(0xFF3B4468),
  onTertiary: Colors.white,
  error: Color(0xFFB3261E),
  onError: Colors.white,
  surface: Brand.page,
  onSurface: Brand.text,
  onSurfaceVariant: Color(0xFF4B5565),
  outline: Color(0xFF8A92A3),
  outlineVariant: Color(0xFFD5D9E3),
  surfaceContainerLowest: Colors.white,
  surfaceContainerLow: Color(0xFFF3F4F8),
  surfaceContainer: Color(0xFFEEF0F5),
  surfaceContainerHigh: Color(0xFFE8EAF1),
  surfaceContainerHighest: Color(0xFFE2E5EE),
  inverseSurface: Brand.navy,
  onInverseSurface: Brand.page,
  inversePrimary: Brand.pinkOnDark,
  surfaceTint: Brand.pink,
  shadow: Colors.black,
  scrim: Colors.black,
);

const _darkScheme = ColorScheme(
  brightness: Brightness.dark,
  primary: Brand.pinkOnDark,
  onPrimary: Color(0xFF3A0020),
  primaryContainer: Color(0xFF8F0F52),
  onPrimaryContainer: Color(0xFFFFD8EA),
  secondary: Color(0xFFC9D0F0),
  onSecondary: Brand.navy,
  secondaryContainer: Color(0xFF2A3A74),
  onSecondaryContainer: Color(0xFFE1E6FA),
  tertiary: Color(0xFFB7BED2),
  onTertiary: Brand.navy,
  error: Color(0xFFFFB4AB),
  onError: Color(0xFF690005),
  surface: Brand.navy,
  onSurface: Color(0xFFF3F4F8),
  onSurfaceVariant: Color(0xFFB7BED2),
  outline: Color(0xFF7C86A8),
  outlineVariant: Color(0xFF2C3A6E),
  surfaceContainerLowest: Color(0xFF0A1230),
  surfaceContainerLow: Color(0xFF111C47),
  surfaceContainer: Color(0xFF15214F),
  surfaceContainerHigh: Color(0xFF1A2858),
  surfaceContainerHighest: Color(0xFF202F63),
  inverseSurface: Color(0xFFE6E9F5),
  onInverseSurface: Brand.navy,
  inversePrimary: Brand.pink,
  surfaceTint: Brand.pinkOnDark,
  shadow: Colors.black,
  scrim: Colors.black,
);

ThemeData appTheme(Brightness brightness) {
  final scheme = brightness == Brightness.dark ? _darkScheme : _lightScheme;
  final base = ThemeData(brightness: brightness, colorScheme: scheme, useMaterial3: true, fontFamily: 'Inter');
  // Headings are heavier and tighter than body; section labels are small capitals (the brand's SECTION HEADER).
  final text = base.textTheme.copyWith(
    headlineMedium: base.textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w700, letterSpacing: -0.5),
    headlineSmall: base.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700, letterSpacing: -0.3),
    titleLarge: base.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700),
    titleMedium: base.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600),
    titleSmall: base.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600),
  );
  return base.copyWith(
    textTheme: text,
    scaffoldBackgroundColor: scheme.surface,
    visualDensity: VisualDensity.standard,
    dividerTheme: DividerThemeData(space: 1, thickness: 1, color: scheme.outlineVariant),
    inputDecorationTheme: InputDecorationTheme(
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide(color: scheme.outline)),
      focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide(color: scheme.primary, width: 2)),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)), textStyle: const TextStyle(fontFamily: 'Inter', fontWeight: FontWeight.w600)),
    ),
    navigationRailTheme: NavigationRailThemeData(
      backgroundColor: scheme.surfaceContainerLowest,
      indicatorColor: scheme.primaryContainer,
      selectedIconTheme: IconThemeData(color: scheme.onPrimaryContainer),
      selectedLabelTextStyle: TextStyle(color: scheme.onSurface, fontWeight: FontWeight.w700, fontSize: 12),
      unselectedLabelTextStyle: TextStyle(color: scheme.onSurfaceVariant, fontSize: 12),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: scheme.surfaceContainerLowest,
      indicatorColor: scheme.primaryContainer,
      labelTextStyle: WidgetStatePropertyAll(TextStyle(color: scheme.onSurface, fontSize: 12, fontWeight: FontWeight.w600)),
    ),
    cardTheme: CardThemeData(
      color: scheme.surfaceContainerLowest,
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12), side: BorderSide(color: scheme.outlineVariant)),
    ),
  );
}

/// Content never grows wider than a comfortable measure, however large the window.
const double kPageMaxWidth = 1100;
const double kWideBreakpoint = 900;
const double kSplitBreakpoint = 1000;
