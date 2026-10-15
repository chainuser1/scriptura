import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import 'version.dart';

/// How to reach Scriptura Labs. Opening a link hands it to the reader's own browser or mail app; the app itself sends nothing.
const String kWebsite = 'https://scriptura.space';
const String kWebsiteLabel = 'scriptura.space';
const String kContactEmail = 'contact@scriptura.space';

/// Opens a link in another app. Tests replace it; it returns false when nothing could open the link.
Future<bool> Function(Uri) launchLink = (uri) => launchUrl(uri, mode: LaunchMode.externalApplication);

Uri contactUri({String? subject}) =>
    Uri.parse('mailto:$kContactEmail${subject == null ? '' : '?subject=${Uri.encodeComponent(subject)}'}');

/// The email for "Report a problem": the version and the kind of device arrive with every report.
Uri reportProblemUri() {
  final device = switch (defaultTargetPlatform) {
    TargetPlatform.android => 'Android',
    TargetPlatform.windows => 'Windows',
    TargetPlatform.iOS => 'iPhone',
    TargetPlatform.macOS => 'Mac',
    _ => 'another device',
  };
  return contactUri(subject: 'Scriptura $kAppVersion on $device: problem');
}

/// Opens [uri]; when no app can, copies [copyText] instead and says so, so the reader is never left with nothing.
Future<void> openOrCopy(BuildContext context, Uri uri, String copyText) async {
  var opened = false;
  try {
    opened = await launchLink(uri);
  } on Object {
    opened = false;
  }
  if (opened || !context.mounted) return;
  final messenger = ScaffoldMessenger.maybeOf(context);
  await Clipboard.setData(ClipboardData(text: copyText));
  messenger?.showSnackBar(SnackBar(content: Text('Copied $copyText')));
}
