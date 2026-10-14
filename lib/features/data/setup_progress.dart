import 'package:flutter/material.dart';

import '../../app_controller.dart';

/// Progress of the automatic data setup with the only two controls it needs: pause, and try again. Shows nothing
/// when no data is missing.
class SetupProgress extends StatelessWidget {
  const SetupProgress({super.key, required this.app});
  final AppController app;

  @override
  Widget build(BuildContext context) {
    final error = Theme.of(context).colorScheme.error;
    switch (app.setupPhase) {
      case SetupPhase.checking:
      case SetupPhase.downloading:
      case SetupPhase.unpacking:
        return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(app.setupLabel),
          const SizedBox(height: 8),
          LinearProgressIndicator(value: app.setupPhase == SetupPhase.downloading ? app.setupFraction : null),
          Align(
            alignment: Alignment.centerRight,
            child: TextButton(onPressed: app.setupPhase == SetupPhase.unpacking ? null : app.pauseSetup, child: const Text('Pause')),
          ),
        ]);
      case SetupPhase.paused:
        return Row(children: [
          const Expanded(child: Text('Paused. Finished parts are kept.')),
          FilledButton(onPressed: () => app.ensureData(includeOptional: app.missingData.contains('colbert') && app.lastRunIncludedOptional), child: const Text('Resume')),
        ]);
      case SetupPhase.failed:
        return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(app.setupError ?? 'Setup did not finish.', style: TextStyle(color: error)),
          const SizedBox(height: 8),
          FilledButton(onPressed: () => app.ensureData(includeOptional: app.lastRunIncludedOptional), child: const Text('Try again')),
        ]);
      case SetupPhase.idle:
        if (app.missingData.isEmpty) return const SizedBox.shrink();
        final onlyIndex = app.missingData.length == 1 && app.missingData.contains('colbert');
        if (onlyIndex) {
          return Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('Sharper results (optional)', style: Theme.of(context).textTheme.titleSmall),
                const SizedBox(height: 4),
                const Text(
                  'The word-level index makes results for subtle wording more precise. It is a large download, about 3 GB: '
                  'best on Wi-Fi. Search works well without it.',
                ),
                const SizedBox(height: 8),
                Wrap(spacing: 8, children: [
                  FilledButton(onPressed: () => app.ensureData(includeOptional: true), child: const Text('Download')),
                  if (app.user.pref('index_declined') != '1') TextButton(onPressed: app.declineOptionalIndex, child: const Text('Not now')),
                ]),
              ]),
            ),
          );
        }
        return Row(children: [
          const Expanded(child: Text('Some data is not on this device yet.')),
          FilledButton(onPressed: app.ensureData, child: const Text('Get it now')),
        ]);
    }
  }
}
