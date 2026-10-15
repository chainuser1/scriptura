import 'package:flutter/material.dart';

import '../../app_controller.dart';
import '../../data/trails/trail_models.dart';
import 'start_trail.dart';
import 'trail_catalog.dart';

const _icons = <String, IconData>{
  'favorite_border': Icons.favorite_border,
  'wb_twilight': Icons.wb_twilight,
  'handshake_outlined': Icons.handshake_outlined,
  'shield_outlined': Icons.shield_outlined,
  'celebration_outlined': Icons.celebration_outlined,
  'spa_outlined': Icons.spa_outlined,
  'explore_outlined': Icons.explore_outlined,
  'volunteer_activism_outlined': Icons.volunteer_activism_outlined,
};

/// Ready-made trails: one tap, no choices (spec 8.2).
class StarterTrails extends StatelessWidget {
  const StarterTrails({super.key, required this.app});
  final AppController app;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return FutureBuilder<TrailCatalog>(
      future: TrailCatalog.shared,
      initialData: TrailCatalog.loaded,
      builder: (context, snap) {
        final catalog = snap.data;
        if (catalog == null) return const SizedBox.shrink();
        Widget card(Starter s) => SizedBox(
              width: 168,
              child: Card(
                margin: EdgeInsets.zero,
                child: InkWell(
                  borderRadius: BorderRadius.circular(12),
                  onTap: () => startTrail(context, app, seed: TrailSeed.question(s.question), name: s.title, moods: [s.moodId]),
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(minHeight: 112),
                    child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Icon(_icons[s.icon] ?? Icons.alt_route, color: Theme.of(context).colorScheme.primary),
                        const SizedBox(height: 8),
                        Text(s.title, style: t.titleSmall),
                        const SizedBox(height: 2),
                        Text(s.blurb, style: t.bodySmall),
                      ]),
                    ),
                  ),
                ),
              ),
            );
        // A phone gets one swipeable row of equal-height cards; a desktop window shows all eight at once.
        final narrow = MediaQuery.sizeOf(context).width < 600;
        return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Semantics(header: true, child: Text('Start a trail', style: t.titleSmall)),
          const SizedBox(height: 4),
          Text('Verses that keep going, shaped by what you like.', style: t.bodySmall),
          const SizedBox(height: 8),
          if (narrow)
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: IntrinsicHeight(
                child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  for (final s in catalog.starters) Padding(padding: const EdgeInsets.only(right: 12), child: card(s)),
                ]),
              ),
            )
          else
            Wrap(spacing: 12, runSpacing: 12, children: [for (final s in catalog.starters) card(s)]),
        ]);
      },
    );
  }
}
