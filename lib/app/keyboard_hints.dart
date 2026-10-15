import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';

/// Keyboard shortcuts are mentioned on desktop and on tablet-sized screens (which often have a keyboard attached), and
/// never on a phone, where the hints would only be noise. The shortcuts themselves still work wherever a keyboard is.
bool showKeyboardHints(BuildContext context) {
  final p = defaultTargetPlatform;
  final desktop = p == TargetPlatform.windows || p == TargetPlatform.linux || p == TargetPlatform.macOS;
  return desktop || MediaQuery.sizeOf(context).shortestSide >= 600;
}
