import 'package:flutter/material.dart';

import '../../app_controller.dart';
import '../../data/trails/trail_models.dart';
import '../../services/engine/search_models.dart';
import 'taste_summary.dart';
import 'trail_catalog.dart';

/// What your likes say, computed on this device from your trail feedback. Nothing here leaves the device.
class TasteScreen extends StatelessWidget {
  const TasteScreen({super.key, required this.app, this.catalog});
  final AppController app;
  final TrailCatalog? catalog;

  Future<({List<FamilyScore> families, TrailCatalog catalog})> _load(List<TrailEvent> events) async {
    final cat = catalog ?? await TrailCatalog.shared;
    if (!app.search.available) return (families: const <FamilyScore>[], catalog: cat);
    final r = await app.search.search(SearchRequest.raw('taste', {
      'events': [for (final e in events) {'verse_id': e.verseId, 'action': e.action.name}],
    }));
    return (families: TasteResult.fromResponse(r), catalog: cat);
  }

  void _reset(BuildContext context) {
    final rows = app.user.clearFeedback();
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: const Text('Your taste was reset'),
      action: SnackBarAction(label: 'Undo', onPressed: () => app.user.restoreFeedback(rows)),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return ListenableBuilder(
      listenable: app.user,
      builder: (context, _) {
        final events = app.user.likeDislikeEvents();
        final liked = [for (final e in events) if (e.action == TrailAction.like) e.verseId];
        return Scaffold(
          appBar: AppBar(
            title: const Text('Your reading taste'),
            actions: [if (events.isNotEmpty) TextButton(onPressed: () => _reset(context), child: const Text('Reset'))],
          ),
          body: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 760),
              child: events.isEmpty
                  ? Padding(padding: const EdgeInsets.all(32), child: Text(tasteSentence(familyLabels: const []), style: t.bodyLarge))
                  : FutureBuilder(
                      future: _load(events),
                      builder: (context, snap) {
                        final data = snap.data;
                        if (data == null) return const Center(child: CircularProgressIndicator());
                        final vols = volumeShares(liked, app.repository!.volumes(language: app.language));
                        final top = data.families.take(2).map((f) => data.catalog.familyLabel(f.family)).toList();
                        final volume = vols.isNotEmpty && vols.first.share >= 0.5 ? 'the ${vols.first.name}' : null;
                        final maxScore = data.families.isEmpty ? 1.0 : data.families.first.score;
                        return ListView(padding: const EdgeInsets.all(24), children: [
                          Text(tasteSentence(familyLabels: top, volumeName: volume), style: t.titleMedium),
                          const SizedBox(height: 20),
                          if (data.families.isNotEmpty) ...[
                            Semantics(header: true, child: Text('What you lean toward', style: t.titleSmall)),
                            const SizedBox(height: 8),
                            for (final f in data.families)
                              Padding(
                                padding: const EdgeInsets.symmetric(vertical: 6),
                                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                                  Text(data.catalog.familyLabel(f.family)),
                                  const SizedBox(height: 4),
                                  LinearProgressIndicator(value: (f.score / maxScore).clamp(0.05, 1.0), minHeight: 8, borderRadius: BorderRadius.circular(4)),
                                ]),
                              ),
                          ] else
                            Text('Family leanings need the search data; the volumes below do not.', style: t.bodySmall),
                          const SizedBox(height: 20),
                          if (vols.isNotEmpty) ...[
                            Semantics(header: true, child: Text('Where your likes come from', style: t.titleSmall)),
                            const SizedBox(height: 8),
                            for (final v in vols)
                              ListTile(dense: true, contentPadding: EdgeInsets.zero, title: Text(v.name), trailing: Text('${(v.share * 100).round()}%')),
                          ],
                          const SizedBox(height: 16),
                          Text('This never leaves your device.', style: t.bodySmall),
                        ]);
                      },
                    ),
            ),
          ),
        );
      },
    );
  }
}
