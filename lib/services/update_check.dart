import 'dart:convert';
import 'dart:io';

/// What the project's latest GitHub release says, compared with the running version.
class UpdateInfo {
  UpdateInfo({required this.current, required this.latest, required this.pageUrl, required this.assets, required this.notes});
  final String current, latest, pageUrl, notes;

  /// asset file name -> direct download URL
  final Map<String, String> assets;

  bool get isNewer => compareVersions(latest, current) > 0;

  /// The installer or package for this platform when the release carries one.
  String? get downloadForThisPlatform {
    final ext = Platform.isWindows ? '.exe' : (Platform.isAndroid ? '.apk' : null);
    if (ext == null) return null;
    for (final e in assets.entries) {
      if (e.key.toLowerCase().endsWith(ext)) return e.value;
    }
    return null;
  }
}

/// Numeric comparison of dotted versions; a leading "v" and any "+build" or "-pre" suffix are ignored.
int compareVersions(String a, String b) {
  List<int> parts(String v) {
    final core = v.trim().replaceFirst(RegExp(r'^[vV]'), '').split(RegExp(r'[+-]')).first;
    return [for (final p in core.split('.')) int.tryParse(p) ?? 0];
  }

  final x = parts(a), y = parts(b);
  for (var i = 0; i < (x.length > y.length ? x.length : y.length); i++) {
    final p = i < x.length ? x[i] : 0, q = i < y.length ? y[i] : 0;
    if (p != q) return p.compareTo(q);
  }
  return 0;
}

UpdateInfo parseRelease(String body, String current) {
  final j = jsonDecode(body) as Map<String, dynamic>;
  final tag = (j['tag_name'] as String?) ?? '';
  if (tag.isEmpty) throw const FormatException('release has no tag_name');
  return UpdateInfo(
    current: current,
    latest: tag.replaceFirst(RegExp(r'^[vV]'), ''),
    pageUrl: (j['html_url'] as String?) ?? '',
    notes: (j['body'] as String?) ?? '',
    assets: {
      for (final a in (j['assets'] as List? ?? const []))
        if (a is Map && a['name'] is String && a['browser_download_url'] is String) a['name'] as String: a['browser_download_url'] as String,
    },
  );
}

/// One anonymous GET of GitHub's latest-release endpoint (no token, nothing about the user sent).
Future<UpdateInfo> checkForUpdate({required String api, required String current, HttpClient? client}) async {
  final http = client ?? (HttpClient()..connectionTimeout = const Duration(seconds: 10));
  try {
    final req = await http.getUrl(Uri.parse(api));
    req.headers.set(HttpHeaders.acceptHeader, 'application/vnd.github+json');
    req.headers.set(HttpHeaders.userAgentHeader, 'Scriptura-update-check');
    final res = await req.close();
    final body = await res.transform(utf8.decoder).join();
    if (res.statusCode == 404) throw const FormatException('no release has been published yet');
    if (res.statusCode != 200) throw HttpException('the release server answered ${res.statusCode}');
    return parseRelease(body, current);
  } finally {
    if (client == null) http.close(force: true);
  }
}
