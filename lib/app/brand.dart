import 'package:flutter/material.dart';

/// Brand tokens (palette taken from the owner's brand kit: navy, one pink accent, a cool grey page).
abstract final class Brand {
  static const navy = Color(0xFF0E183E);
  static const pink = Color(0xFFD3167B);
  static const pinkOnDark = Color(0xFFF06DAE); // pink passes 4.5:1 on navy only as a lighter tint
  static const page = Color(0xFFF9FAFB);
  static const ink = Color(0xFF2C2C2C);
  static const text = Color(0xFF111827);
}

/// The Scriptura mark: an open book under one lit point. Structure in ink, exactly one pink accent (the brand's icon
/// grammar). Drawn here so it scales crisply everywhere; tool/make_icon.py draws the same geometry for the app icon.
class ScripturesMark extends StatelessWidget {
  const ScripturesMark({super.key, this.size = 40, this.onDark = false, this.semanticLabel});
  final double size;
  final bool onDark;

  /// Null makes the mark decorative (hidden from screen readers).
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    final mark = CustomPaint(
      size: Size.square(size),
      painter: _MarkPainter(ink: onDark ? Colors.white : Brand.navy, accent: onDark ? Brand.pinkOnDark : Brand.pink),
    );
    if (semanticLabel == null) return ExcludeSemantics(child: mark);
    return Semantics(label: semanticLabel, image: true, child: ExcludeSemantics(child: mark));
  }
}

class _MarkPainter extends CustomPainter {
  _MarkPainter({required this.ink, required this.accent});
  final Color ink, accent;

  @override
  void paint(Canvas canvas, Size size) {
    final u = size.width / 100;
    Offset p(double x, double y) => Offset(x * u, y * u);
    final stroke = Paint()
      ..color = ink
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round
      ..strokeWidth = 3.6 * u;
    final fine = Paint.from(stroke)..strokeWidth = 2.4 * u;
    for (final m in [-1.0, 1.0]) {
      double x(double v) => 50 + m * v;
      final page = Path()
        ..moveTo(p(50, 40).dx, p(50, 40).dy)
        ..lineTo(p(x(36), 31).dx, p(x(36), 31).dy)
        ..lineTo(p(x(36), 76).dx, p(x(36), 76).dy)
        ..lineTo(p(50, 85).dx, p(50, 85).dy)
        ..close();
      canvas.drawPath(page, stroke);
      for (var i = 0; i < 3; i++) {
        final y = 46.0 + i * 10;
        canvas.drawLine(p(x(28), y), p(x(8), y + 4.5), fine);
      }
    }
    canvas.drawLine(p(50, 24), p(50, 40), fine);
    canvas.drawCircle(p(50, 17), 7 * u, Paint()..color = accent);
  }

  @override
  bool shouldRepaint(_MarkPainter old) => old.ink != ink || old.accent != accent;
}
