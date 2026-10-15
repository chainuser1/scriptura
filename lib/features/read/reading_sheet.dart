import 'package:flutter/material.dart';

import '../../app/nav_state.dart';
import '../../app/theme.dart';
import '../../app_controller.dart';
import '../settings/reading_controls.dart';

/// The reader's quick "Aa" menu: pick a look, nudge size, colour, typeface and spacing without leaving the page. Narrow
/// windows get a bottom sheet, wide ones a panel at the top right so the text stays visible while you adjust it.
Future<void> showReadingSheet(BuildContext context, AppController app) {
  final wide = MediaQuery.sizeOf(context).width >= kWideBreakpoint;
  Widget body(BuildContext ctx) => SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Expanded(child: Semantics(header: true, child: Text('Reading look', style: Theme.of(ctx).textTheme.titleMedium))),
            IconButton(tooltip: 'Close', icon: const Icon(Icons.close), onPressed: () => Navigator.of(ctx).pop()),
          ]),
          const SizedBox(height: 8),
          LookGallery(user: app.user),
          ReadingControls(user: app.user, compact: true),
          const SizedBox(height: 8),
          TextButton.icon(
            onPressed: () {
              Navigator.of(ctx).pop();
              app.nav.go(Dest.settings);
            },
            icon: const Icon(Icons.tune),
            label: const Text('All reading settings'),
          ),
        ]),
      );
  if (wide) {
    return showDialog<void>(
      context: context,
      barrierColor: Colors.transparent,
      builder: (ctx) => Dialog(alignment: Alignment.topRight, insetPadding: const EdgeInsets.fromLTRB(24, 64, 24, 24), child: SizedBox(width: 440, child: body(ctx))),
    );
  }
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    // SafeArea: on phones the sheet's last controls stay above the system navigation bar
    builder: (ctx) => SafeArea(top: false, child: ConstrainedBox(constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(ctx).height * 0.85), child: body(ctx))),
  );
}
