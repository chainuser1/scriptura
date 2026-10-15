import 'package:flutter/material.dart';

import '../../app_controller.dart';
import '../../data/trails/trail_models.dart';
import 'start_trail.dart';
import 'taste_screen.dart';

class TrailsTab extends StatelessWidget {
  const TrailsTab({super.key, required this.app});
  final AppController app;

  String _subtitle(Trail t) {
    final seed = switch (t.seed.kind) {
      TrailSeedKind.verse => 'from a verse',
      TrailSeedKind.question => 'about “${t.seed.text}”',
      _ => 'about ${t.seed.text ?? 'a name'}',
    };
    final events = app.user.trailEvents(t.id);
    final liked = events.where((e) => e.action == TrailAction.like).length;
    return '$seed · ${events.where((e) => e.action == TrailAction.shown).length} verses · $liked liked';
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: app.user,
      builder: (context, _) {
        final trails = app.user.trails();
        return Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 900),
            child: ListView(padding: const EdgeInsets.symmetric(vertical: 8), children: [
              ListTile(
                leading: const Icon(Icons.insights_outlined),
                title: const Text('Your reading taste'),
                subtitle: const Text('What your likes say about you, on this device only'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => TasteScreen(app: app))),
              ),
              const Divider(),
              if (trails.isEmpty)
                const Padding(
                  padding: EdgeInsets.all(32),
                  child: Column(children: [
                    Icon(Icons.alt_route, size: 40),
                    SizedBox(height: 12),
                    Text('No trails yet'),
                    SizedBox(height: 4),
                    Text('Start one from Home, or choose “Start a trail from this verse” in any verse’s menu.', textAlign: TextAlign.center),
                  ]),
                ),
              for (final t in trails)
                ListTile(
                  key: ValueKey('trail-${t.id}'),
                  leading: const Icon(Icons.alt_route),
                  title: Text(t.name, overflow: TextOverflow.ellipsis),
                  subtitle: Text(_subtitle(t), overflow: TextOverflow.ellipsis),
                  onTap: () => openTrail(context, app, t),
                  trailing: PopupMenuButton<String>(
                    tooltip: 'More',
                    onSelected: (v) {
                      if (v == 'delete') {
                        final snap = app.user.deleteTrail(t.id);
                        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                          content: const Text('Trail deleted'),
                          action: SnackBarAction(label: 'Undo', onPressed: () => app.user.restoreTrail(snap)),
                        ));
                      }
                    },
                    itemBuilder: (_) => const [PopupMenuItem(value: 'delete', child: Text('Delete'))],
                  ),
                ),
            ]),
          ),
        );
      },
    );
  }
}
