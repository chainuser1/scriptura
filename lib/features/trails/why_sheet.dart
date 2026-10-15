import 'package:flutter/material.dart';

import '../../app/theme.dart';
import 'trail_controller.dart';
import 'trail_reasons.dart';

IconData _icon(ReasonKind k) => switch (k) {
      ReasonKind.themes => Icons.auto_awesome_outlined,
      ReasonKind.mood => Icons.mood_outlined,
      ReasonKind.words => Icons.format_quote,
      ReasonKind.people => Icons.link, // people, places and groups alike
      ReasonKind.question => Icons.help_outline,
      ReasonKind.taste => Icons.thumb_up_outlined,
      ReasonKind.variety => Icons.shuffle,
    };

/// Narrow: a bottom sheet. Wide: a 360 px panel on the right so the card stays visible.
Future<void> showWhy(BuildContext context, TrailController c) {
  final wide = MediaQuery.sizeOf(context).width >= kWideBreakpoint;
  if (wide) {
    return showGeneralDialog<void>(
      context: context,
      barrierDismissible: true,
      barrierLabel: 'Close',
      barrierColor: Colors.black.withValues(alpha: 0.32), // dim the trail: the panel reads as on top, not as cutting the card
      transitionDuration: MediaQuery.disableAnimationsOf(context) ? Duration.zero : const Duration(milliseconds: 180),
      pageBuilder: (ctx, _, __) => Align(
        alignment: Alignment.centerRight,
        child: Material(
          color: Theme.of(ctx).colorScheme.surface,
          child: Container(
            width: 360,
            height: double.infinity,
            decoration: BoxDecoration(border: Border(left: BorderSide(color: Theme.of(ctx).colorScheme.outlineVariant))),
            child: SafeArea(child: _WhyBody(controller: c)),
          ),
        ),
      ),
    );
  }
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (_) => ConstrainedBox(
      constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.75),
      child: _WhyBody(controller: c),
    ),
  );
}

class _WhyBody extends StatelessWidget {
  const _WhyBody({required this.controller});
  final TrailController controller;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 8, 12, 16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(child: Semantics(header: true, child: Text('Why this verse is here', style: t.titleMedium))),
          IconButton(tooltip: 'Close', icon: const Icon(Icons.close), onPressed: () => Navigator.of(context).pop()),
        ]),
        const SizedBox(height: 8),
        Expanded(
          child: FutureBuilder<List<Reason>>(
            future: controller.why(),
            builder: (context, snap) {
              if (snap.connectionState != ConnectionState.done) return const Center(child: CircularProgressIndicator());
              final reasons = snap.data ?? const [];
              if (reasons.isEmpty) {
                return Text('No specific reason is known for this verse yet. It sits close to your trail in the overall picture.', style: t.bodyMedium);
              }
              return ListView(children: [
                for (final r in reasons)
                  r.detail.isEmpty
                      ? ListTile(leading: Icon(_icon(r.kind)), title: SelectableText(r.text), contentPadding: EdgeInsets.zero)
                      : ExpansionTile(
                          leading: Icon(_icon(r.kind)),
                          title: Text(r.text),
                          tilePadding: EdgeInsets.zero,
                          childrenPadding: const EdgeInsets.only(left: 40, bottom: 8),
                          expandedCrossAxisAlignment: CrossAxisAlignment.start,
                          children: [for (final d in r.detail) Padding(padding: const EdgeInsets.only(bottom: 4), child: SelectableText(d, style: t.bodySmall))],
                        ),
              ]);
            },
          ),
        ),
      ]),
    );
  }
}
