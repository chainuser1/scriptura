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

/// The app's overall style (the window chrome: colours, typefaces, shapes). It is design only: every theme shows the
/// same screens, controls, words and logo; the reading page keeps its own look. Scriptura is today's look.
enum AppStyle {
  scriptura('Scriptura', 'Our own look: navy, one pink accent, clean type.'),
  classic('Classic', 'A printed book: warm paper, old-style serif, oxblood ink.'),
  modern('Modern', 'Bold type, soft pills, a navy bar.'),
  elegant('Elegant', 'Night and gold, a fine serif, quiet lines.'),
  aesthetic('Aesthetic', 'Blush and lilac, rounded type, soft cards.');

  const AppStyle(this.label, this.blurb);
  final String label, blurb;

  /// Elegant is a night theme; the others follow the system's light or dark setting.
  ThemeMode get mode => this == elegant ? ThemeMode.dark : ThemeMode.system;

  static AppStyle parse(String? s) => values.firstWhere((t) => t.name == s, orElse: () => AppStyle.scriptura);
}

ColorScheme _scheme(
  Brightness b, {
  required Color primary,
  required Color onPrimary,
  required Color primaryContainer,
  required Color onPrimaryContainer,
  required Color secondary,
  required Color onSecondary,
  required Color secondaryContainer,
  required Color onSecondaryContainer,
  required Color surface,
  required Color onSurface,
  required Color onSurfaceVariant,
  required Color outline,
  required Color outlineVariant,
  required List<Color> containers, // lowest, low, base, high, highest
}) =>
    ColorScheme(
      brightness: b,
      primary: primary,
      onPrimary: onPrimary,
      primaryContainer: primaryContainer,
      onPrimaryContainer: onPrimaryContainer,
      secondary: secondary,
      onSecondary: onSecondary,
      secondaryContainer: secondaryContainer,
      onSecondaryContainer: onSecondaryContainer,
      tertiary: secondary,
      onTertiary: onSecondary,
      error: b == Brightness.dark ? const Color(0xFFFFB4AB) : const Color(0xFFB3261E),
      onError: b == Brightness.dark ? const Color(0xFF690005) : Colors.white,
      surface: surface,
      onSurface: onSurface,
      onSurfaceVariant: onSurfaceVariant,
      outline: outline,
      outlineVariant: outlineVariant,
      surfaceContainerLowest: containers[0],
      surfaceContainerLow: containers[1],
      surfaceContainer: containers[2],
      surfaceContainerHigh: containers[3],
      surfaceContainerHighest: containers[4],
      inverseSurface: onSurface,
      onInverseSurface: surface,
      inversePrimary: primaryContainer,
      surfaceTint: primary,
      shadow: Colors.black,
      scrim: Colors.black,
    );

final _classicLight = _scheme(Brightness.light,
    primary: const Color(0xFF9C1D3F),
    onPrimary: Colors.white,
    primaryContainer: const Color(0xFFEFD6D3),
    onPrimaryContainer: const Color(0xFF4A0A1C),
    secondary: const Color(0xFF2A1F1A),
    onSecondary: Colors.white,
    secondaryContainer: const Color(0xFFE6DCC6),
    onSecondaryContainer: const Color(0xFF2A1F1A),
    surface: const Color(0xFFF3ECDD),
    onSurface: const Color(0xFF2A1F1A),
    onSurfaceVariant: const Color(0xFF5E5245),
    outline: const Color(0xFF7F705E),
    outlineVariant: const Color(0xFFCDBFA5),
    containers: const [Color(0xFFFBF6EC), Color(0xFFEFE6D3), Color(0xFFEAE0CA), Color(0xFFE4D9C1), Color(0xFFDED2B8)]);
final _classicDark = _scheme(Brightness.dark,
    primary: const Color(0xFFE79AAD),
    onPrimary: const Color(0xFF4A0A1C),
    primaryContainer: const Color(0xFF6E1530),
    onPrimaryContainer: const Color(0xFFFFD9DF),
    secondary: const Color(0xFFE2D5BC),
    onSecondary: const Color(0xFF2A1F1A),
    secondaryContainer: const Color(0xFF3A3128),
    onSecondaryContainer: const Color(0xFFEDE3D0),
    surface: const Color(0xFF1E1914),
    onSurface: const Color(0xFFEDE3D0),
    onSurfaceVariant: const Color(0xFFC9BBA4),
    outline: const Color(0xFF8C7B66),
    outlineVariant: const Color(0xFF4A3F33),
    containers: const [Color(0xFF17130F), Color(0xFF241E18), Color(0xFF2A231C), Color(0xFF312920), Color(0xFF382F25)]);

final _modernLight = _scheme(Brightness.light,
    primary: Brand.pink,
    onPrimary: Colors.white,
    primaryContainer: const Color(0xFFFCE4EF),
    onPrimaryContainer: const Color(0xFF5E0A37),
    secondary: Brand.navy,
    onSecondary: Colors.white,
    secondaryContainer: const Color(0xFFE6E9F5),
    onSecondaryContainer: Brand.navy,
    surface: Colors.white,
    onSurface: Brand.navy,
    onSurfaceVariant: const Color(0xFF4B5068),
    outline: const Color(0xFF8A92A3),
    outlineVariant: const Color(0xFFE3E6EE),
    containers: const [Colors.white, Color(0xFFF7F8FA), Color(0xFFF1F2F6), Color(0xFFEAECF2), Color(0xFFE3E6EE)]);
final _modernDark = _scheme(Brightness.dark,
    primary: Brand.pinkOnDark,
    onPrimary: const Color(0xFF3A0020),
    primaryContainer: const Color(0xFF8F0F52),
    onPrimaryContainer: const Color(0xFFFFD8EA),
    secondary: const Color(0xFFC9D0F0),
    onSecondary: Brand.navy,
    secondaryContainer: const Color(0xFF2A3A74),
    onSecondaryContainer: const Color(0xFFE1E6FA),
    surface: const Color(0xFF0B1130),
    onSurface: const Color(0xFFF3F4F8),
    onSurfaceVariant: const Color(0xFFB7BED2),
    outline: const Color(0xFF7C86A8),
    outlineVariant: const Color(0xFF2C3A6E),
    containers: const [Color(0xFF070B20), Color(0xFF10173A), Color(0xFF151D45), Color(0xFF1B2450), Color(0xFF212B5B)]);

final _elegant = _scheme(Brightness.dark,
    primary: const Color(0xFFC9AE7C),
    onPrimary: const Color(0xFF2A2110),
    primaryContainer: const Color(0xFF3A3122),
    onPrimaryContainer: const Color(0xFFF1E2C4),
    secondary: const Color(0xFFC9AE7C),
    onSecondary: const Color(0xFF2A2110),
    secondaryContainer: const Color(0xFF2A2C38),
    onSecondaryContainer: const Color(0xFFEDE6D8),
    surface: const Color(0xFF11131C),
    onSurface: const Color(0xFFEDE6D8),
    onSurfaceVariant: const Color(0xFFA39C8F),
    outline: const Color(0xFF7A6E58),
    outlineVariant: const Color(0xFF2A2C38),
    containers: const [Color(0xFF0C0E15), Color(0xFF161822), Color(0xFF1A1C27), Color(0xFF1F212D), Color(0xFF252734)]);

final _aestheticLight = _scheme(Brightness.light,
    primary: Brand.pink,
    onPrimary: Colors.white,
    primaryContainer: const Color(0xFFFCE4EF),
    onPrimaryContainer: const Color(0xFF5E0A37),
    secondary: const Color(0xFF3A2E4F),
    onSecondary: Colors.white,
    secondaryContainer: const Color(0xFFE4E0F5),
    onSecondaryContainer: const Color(0xFF3A2E4F),
    surface: const Color(0xFFFBF0F3),
    onSurface: const Color(0xFF3A2E4F),
    onSurfaceVariant: const Color(0xFF64587A),
    outline: const Color(0xFF9A8FAB),
    outlineVariant: const Color(0xFFEAD9E2),
    containers: const [Colors.white, Color(0xFFFDF6F8), Color(0xFFF7E9EE), Color(0xFFF2E1E8), Color(0xFFECD9E2)]);
final _aestheticDark = _scheme(Brightness.dark,
    primary: Brand.pinkOnDark,
    onPrimary: const Color(0xFF3A0020),
    primaryContainer: const Color(0xFF6E1A4A),
    onPrimaryContainer: const Color(0xFFFFD8EA),
    secondary: const Color(0xFFD9D0F0),
    onSecondary: const Color(0xFF3A2E4F),
    secondaryContainer: const Color(0xFF3E3450),
    onSecondaryContainer: const Color(0xFFF3EAF2),
    surface: const Color(0xFF221B2E),
    onSurface: const Color(0xFFF3EAF2),
    onSurfaceVariant: const Color(0xFFC9BDD6),
    outline: const Color(0xFF8F82A3),
    outlineVariant: const Color(0xFF463B57),
    containers: const [Color(0xFF1B1525), Color(0xFF2A2238), Color(0xFF30273F), Color(0xFF372D47), Color(0xFF3E3450)]);

/// The colours a theme uses for [brightness] (Elegant is always its night palette).
ColorScheme schemeFor(AppStyle style, Brightness brightness) {
  final dark = brightness == Brightness.dark;
  return switch (style) {
    AppStyle.scriptura => dark ? _darkScheme : _lightScheme,
    AppStyle.classic => dark ? _classicDark : _classicLight,
    AppStyle.modern => dark ? _modernDark : _modernLight,
    AppStyle.elegant => _elegant,
    AppStyle.aesthetic => dark ? _aestheticDark : _aestheticLight,
  };
}

/// Built once per theme and brightness, so a preference change elsewhere never rebuilds the whole app's look.
ThemeData appTheme(Brightness brightness, [AppStyle style = AppStyle.scriptura]) => _themes[(brightness, style)] ??= _buildTheme(brightness, style);
final _themes = <(Brightness, AppStyle), ThemeData>{};

ThemeData _buildTheme(Brightness brightness, AppStyle style) {
  final scheme = schemeFor(style, brightness);
  // The body face, and the face for headings and titles.
  final (body, display) = switch (style) {
    AppStyle.scriptura => ('Inter', 'Inter'),
    AppStyle.classic => ('EBGaramond', 'EBGaramond'),
    AppStyle.modern => ('PlusJakartaSans', 'PlusJakartaSans'),
    AppStyle.elegant => ('Jost', 'CormorantGaramond'),
    AppStyle.aesthetic => ('Nunito', 'Fraunces'),
  };
  // Corners of fields and buttons (null: fully rounded pills), and of cards.
  final double? radius = switch (style) {
    AppStyle.scriptura => 10,
    AppStyle.classic => 3,
    AppStyle.modern || AppStyle.elegant => null,
    AppStyle.aesthetic => 20,
  };
  final double cardRadius = switch (style) {
    AppStyle.scriptura => 12,
    AppStyle.classic => 3,
    AppStyle.modern => 22,
    AppStyle.elegant => 4,
    AppStyle.aesthetic => 24,
  };
  final OutlinedBorder buttonShape = radius == null ? const StadiumBorder() : RoundedRectangleBorder(borderRadius: BorderRadius.circular(radius));
  final field = BorderRadius.circular(radius ?? 28);
  final base = ThemeData(brightness: scheme.brightness, colorScheme: scheme, useMaterial3: true, fontFamily: body);
  final weight = switch (style) {
    AppStyle.elegant => FontWeight.w500,
    AppStyle.classic => FontWeight.w600,
    AppStyle.modern => FontWeight.w800,
    _ => FontWeight.w700,
  };
  final scriptura = style == AppStyle.scriptura;
  final tight = style == AppStyle.modern ? -0.8 : 0.0;
  // Headings are heavier and tighter than body; section labels are small capitals (the brand's SECTION HEADER).
  final text = base.textTheme.copyWith(
    headlineMedium: base.textTheme.headlineMedium?.copyWith(fontFamily: display, fontWeight: weight, letterSpacing: scriptura ? -0.5 : tight),
    headlineSmall: base.textTheme.headlineSmall?.copyWith(fontFamily: display, fontWeight: weight, letterSpacing: scriptura ? -0.3 : tight),
    titleLarge: base.textTheme.titleLarge?.copyWith(fontFamily: display, fontWeight: style == AppStyle.modern ? FontWeight.w700 : weight),
    titleMedium: base.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600),
    titleSmall: base.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600),
  );
  // Modern sets the navigation on a navy bar; Classic and Elegant on the page itself; the others on a white strip.
  final navyBar = style == AppStyle.modern && scheme.brightness == Brightness.light;
  final gold = style == AppStyle.elegant;
  final navBg = navyBar
      ? Brand.navy
      : style == AppStyle.classic || gold
          ? scheme.surface
          : scheme.surfaceContainerLowest;
  final navOff = navyBar ? const Color(0xFFC9D0F0) : scheme.onSurfaceVariant;
  final navLabel = navyBar ? Colors.white : gold ? scheme.primary : scheme.onSurface;
  final indicator = navyBar ? Brand.pink : gold ? Colors.transparent : scheme.primaryContainer;
  final selectedIcon = navyBar ? Colors.white : gold ? scheme.primary : scheme.onPrimaryContainer;
  return base.copyWith(
    textTheme: text,
    scaffoldBackgroundColor: scheme.surface,
    visualDensity: VisualDensity.standard,
    dividerTheme: DividerThemeData(space: 1, thickness: 1, color: scheme.outlineVariant),
    inputDecorationTheme: InputDecorationTheme(
      filled: style == AppStyle.modern || style == AppStyle.aesthetic ? true : null,
      fillColor: style == AppStyle.modern
          ? scheme.surfaceContainer
          : style == AppStyle.aesthetic
              ? scheme.surfaceContainerLowest
              : null,
      border: OutlineInputBorder(borderRadius: field),
      enabledBorder: OutlineInputBorder(borderRadius: field, borderSide: BorderSide(color: scheme.outline)),
      focusedBorder: OutlineInputBorder(borderRadius: field, borderSide: BorderSide(color: scheme.primary, width: 2)),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(shape: buttonShape, textStyle: TextStyle(fontFamily: body, fontWeight: FontWeight.w600)),
    ),
    navigationRailTheme: NavigationRailThemeData(
      backgroundColor: navBg,
      indicatorColor: indicator,
      selectedIconTheme: IconThemeData(color: selectedIcon),
      unselectedIconTheme: navyBar ? IconThemeData(color: navOff) : null,
      // The rail's labels do not inherit the app face; the new themes set it (Scriptura keeps today's labels).
      selectedLabelTextStyle: TextStyle(fontFamily: scriptura ? null : body, color: navLabel, fontWeight: FontWeight.w700, fontSize: 12),
      unselectedLabelTextStyle: TextStyle(fontFamily: scriptura ? null : body, color: navOff, fontSize: 12),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: navBg,
      indicatorColor: indicator,
      iconTheme: navyBar || gold ? WidgetStateProperty.resolveWith((s) => IconThemeData(color: s.contains(WidgetState.selected) ? selectedIcon : navOff)) : null,
      labelTextStyle: gold
          ? WidgetStateProperty.resolveWith((s) => TextStyle(color: s.contains(WidgetState.selected) ? navLabel : navOff, fontSize: 12, fontWeight: FontWeight.w600))
          : WidgetStatePropertyAll(TextStyle(color: navLabel, fontSize: 12, fontWeight: FontWeight.w600)),
    ),
    cardTheme: CardThemeData(
      color: style == AppStyle.modern ? scheme.surfaceContainer : scheme.surfaceContainerLowest,
      elevation: style == AppStyle.aesthetic ? 2 : 0,
      shadowColor: style == AppStyle.aesthetic ? scheme.secondary.withValues(alpha: 0.25) : null,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(cardRadius),
        side: style == AppStyle.modern || style == AppStyle.aesthetic ? BorderSide.none : BorderSide(color: scheme.outlineVariant),
      ),
    ),
  );
}

/// Content never grows wider than a comfortable measure, however large the window.
const double kPageMaxWidth = 1100;
const double kWideBreakpoint = 900;
const double kSplitBreakpoint = 1000;
