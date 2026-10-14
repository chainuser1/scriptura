import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/services/update_check.dart';

void main() {
  test('versions compare numerically, ignoring v, build and pre-release suffixes', () {
    expect(compareVersions('1.0.0', '1.0.0'), 0);
    expect(compareVersions('v1.2.0', '1.1.9'), greaterThan(0));
    expect(compareVersions('1.10.0', '1.9.0'), greaterThan(0));
    expect(compareVersions('1.0', '1.0.0'), 0);
    expect(compareVersions('2.0.0-beta.1', '1.9.9'), greaterThan(0));
    expect(compareVersions('1.0.0+7', '1.0.0'), 0);
    expect(compareVersions('0.9.0', '1.0.0'), lessThan(0));
  });

  test('a GitHub latest-release document is read for tag, page and assets', () {
    final body = jsonEncode({
      'tag_name': 'v1.2.0',
      'html_url': 'https://github.com/o/r/releases/tag/v1.2.0',
      'body': 'Notes',
      'assets': [
        {'name': 'Scriptura-Setup.exe', 'browser_download_url': 'https://github.com/o/r/releases/download/v1.2.0/Scriptura-Setup.exe'},
        {'name': 'Scriptura.apk', 'browser_download_url': 'https://github.com/o/r/releases/download/v1.2.0/Scriptura.apk'},
        {'name': 'broken'},
      ],
    });
    final u = parseRelease(body, '1.0.0');
    expect(u.latest, '1.2.0');
    expect(u.isNewer, isTrue);
    expect(u.assets.keys, ['Scriptura-Setup.exe', 'Scriptura.apk']);
    expect(parseRelease(body, '1.2.0').isNewer, isFalse);
    expect(() => parseRelease('{"html_url":"x"}', '1.0.0'), throwsFormatException);
  });
}
