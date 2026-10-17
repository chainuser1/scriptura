import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

/// Quick search from anywhere on Windows: the runner registers Ctrl+Alt+Space with the system and, while
/// "keep running in the tray" is on, hides the window on close instead of quitting (windows/runner/flutter_window.cpp).
abstract final class Desktop {
  static const _channel = MethodChannel('scriptura/desktop');
  static bool get supported => !kIsWeb && Platform.isWindows;

  /// Whether Ctrl+Alt+Space is ours; false when another program holds it, null until known or off Windows.
  static final hotkey = ValueNotifier<bool?>(null);

  static void onQuickSearch(VoidCallback open) => _channel.setMethodCallHandler((call) async {
        if (call.method == 'quickSearch') open();
      });

  static Future<void> configure({required bool background}) async {
    if (!supported) return;
    try {
      final r = await _channel.invokeMapMethod<String, Object?>('configure', {'background': background});
      hotkey.value = r?['hotkey'] as bool?;
    } on MissingPluginException {
      // not running in the Windows app (tests)
    } on PlatformException {
      // leave the state unknown
    }
  }
}
