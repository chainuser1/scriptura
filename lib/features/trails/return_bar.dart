import 'package:flutter/material.dart';

import '../../app_controller.dart';
import '../../data/trails/trail_models.dart';
import 'start_trail.dart';

/// A thin "back to your trail" bar, visible on every screen while a trail has activity and the Trail page is not showing.
class ReturnBar extends StatelessWidget {
  const ReturnBar({super.key, required this.app});
  final AppController app;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: Listenable.merge([app, app.nav, app.user]),
      builder: (context, _) {
        final id = app.user.pref('active_trail');
        if (id == null || id.isEmpty || app.nav.trailOpen || app.repository == null) return const SizedBox.shrink();
        final trail = app.user.trail(id);
        if (trail == null) return const SizedBox.shrink();
        final events = app.user.trailEvents(id);
        final shown = events.where((e) => e.action == TrailAction.shown).toList();
        if (shown.isEmpty) return const SizedBox.shrink();
        String where;
        try {
          where = app.repository!.getPassage(shown.last.verseId, language: app.language).reference;
        } on Object {
          where = '';
        }
        final scheme = Theme.of(context).colorScheme;
        return Material(
          color: scheme.secondaryContainer,
          child: SizedBox(
            height: 52,
            child: Row(children: [
              const SizedBox(width: 16),
              Icon(Icons.alt_route, color: scheme.onSecondaryContainer),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  where.isEmpty ? trail.name : '${trail.name} · $where',
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(color: scheme.onSecondaryContainer, fontWeight: FontWeight.w600),
                ),
              ),
              TextButton(onPressed: () => openTrail(context, app, trail), child: const Text('Resume')),
              IconButton(tooltip: 'Dismiss', icon: const Icon(Icons.close), onPressed: () => app.user.setPref('active_trail', '')),
            ]),
          ),
        );
      },
    );
  }
}
