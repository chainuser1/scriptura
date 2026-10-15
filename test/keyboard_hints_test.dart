import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app/keyboard_hints.dart';

Future<bool> hintsAt(WidgetTester tester, Size size, TargetPlatform platform) async {
  debugDefaultTargetPlatformOverride = platform;
  late bool shown;
  await tester.pumpWidget(MediaQuery(
    data: MediaQueryData(size: size),
    child: Builder(builder: (context) {
      shown = showKeyboardHints(context);
      return const SizedBox();
    }),
  ));
  debugDefaultTargetPlatformOverride = null; // must be unset before the test ends
  return shown;
}

void main() {
  testWidgets('phones never see keyboard hints; tablets and desktops do', (tester) async {
    expect(await hintsAt(tester, const Size(390, 844), TargetPlatform.android), isFalse);
    expect(await hintsAt(tester, const Size(360, 640), TargetPlatform.iOS), isFalse);
    expect(await hintsAt(tester, const Size(800, 1280), TargetPlatform.android), isTrue);
    expect(await hintsAt(tester, const Size(1366, 768), TargetPlatform.windows), isTrue);
    expect(await hintsAt(tester, const Size(480, 700), TargetPlatform.windows), isTrue); // a narrow desktop window
  });
}
