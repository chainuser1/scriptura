import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app/contact.dart';
import 'package:scriptures_reader_mobile/app/nav_state.dart';
import 'package:scriptures_reader_mobile/app/theme.dart';
import 'package:scriptures_reader_mobile/app/version.dart';
import 'package:scriptures_reader_mobile/features/about/about_screen.dart';

import 'looks_ui_test.dart' show boot;

void main() {
  late List<Uri> opened;
  var canOpen = true;
  setUp(() {
    opened = [];
    canOpen = true;
    launchLink = (uri) async {
      opened.add(uri);
      return canOpen;
    };
  });

  test('a problem report names the version and the device, with spaces encoded for mail apps', () {
    final uri = reportProblemUri().toString();
    expect(uri, startsWith('mailto:contact@scriptura.space?subject='));
    expect(Uri.decodeComponent(uri.split('subject=')[1]), 'Scriptura $kAppVersion on Android: problem');
    expect(uri, isNot(contains('+')));
  });

  Future<void> settings(WidgetTester tester) async {
    final app = await boot(tester, size: const Size(420, 900));
    app.nav.go(Dest.settings);
    await tester.pumpAndSettle();
  }

  Future<void> tapRow(WidgetTester tester, String title) async {
    await tester.scrollUntilVisible(find.text(title), 300, scrollable: find.byType(Scrollable).first);
    await tester.ensureVisible(find.text(title)); // bring it clear of the bottom bar before tapping
    await tester.pumpAndSettle();
    await tester.tap(find.text(title));
    await tester.pumpAndSettle();
  }

  testWidgets('Settings, About: website, contact and report a problem open the right place', (tester) async {
    await settings(tester);
    await tester.scrollUntilVisible(find.text('Why Scriptura exists'), 300, scrollable: find.byType(Scrollable).first);
    await tapRow(tester, 'Website');
    await tapRow(tester, 'Contact us');
    await tapRow(tester, 'Report a problem');
    expect(opened.map((u) => u.toString()).toList(), [
      'https://scriptura.space',
      'mailto:contact@scriptura.space',
      reportProblemUri().toString(),
    ]);
  });

  testWidgets('with no mail app, the address is copied and the reader is told', (tester) async {
    String? copied;
    canOpen = false;
    await settings(tester);
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
      if (call.method == 'Clipboard.setData') copied = (call.arguments as Map)['text'] as String;
      return null;
    });
    addTearDown(() => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, null));
    await tapRow(tester, 'Contact us');
    expect(copied, 'contact@scriptura.space');
    expect(find.text('Copied contact@scriptura.space'), findsOneWidget);
  });

  testWidgets('Our story ends with a way to get in touch', (tester) async {
    tester.view.physicalSize = const Size(1100, 4000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(theme: appTheme(Brightness.light), home: const AboutScreen()));
    expect(find.text('GET IN TOUCH'), findsOneWidget);
    await tester.tap(find.text(kContactEmail));
    await tester.tap(find.text(kWebsiteLabel));
    await tester.pumpAndSettle();
    expect(opened.map((u) => u.toString()).toList(), ['mailto:contact@scriptura.space', 'https://scriptura.space']);
  });
}
