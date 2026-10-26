import 'package:flutter/material.dart';

/// App-accent selection colors adapted to the independent reading surface.
class PassageColors {
  factory PassageColors(ColorScheme scheme,
      {required Color surface, required Color text}) {
    var marker = scheme.primary;
    // A night-app accent can be too pale on paper (or vice versa). Keep its hue
    // while moving toward the page ink only as far as visibility requires.
    for (var step = 1; _contrast(marker, surface) < 3 && step <= 10; step++) {
      marker = Color.lerp(scheme.primary, text, step / 10)!;
    }
    return PassageColors._(
      scheme.primary,
      scheme.onPrimary,
      marker,
      Color.alphaBlend(scheme.primary.withValues(alpha: 0.10), surface),
      Color.alphaBlend(scheme.primary.withValues(alpha: 0.04), surface),
    );
  }

  const PassageColors._(
      this.accent, this.onAccent, this.marker, this.activeFill, this.matchFill);

  final Color accent, onAccent, marker, activeFill, matchFill;

  static double _contrast(Color a, Color b) {
    final x = a.computeLuminance(), y = b.computeLuminance();
    return (x > y ? x + 0.05 : y + 0.05) / (x > y ? y + 0.05 : x + 0.05);
  }
}
