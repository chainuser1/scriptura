import 'package:flutter/material.dart';

import '../../app/brand.dart';
import '../../app_controller.dart';
import '../data/setup_progress.dart';

/// Shown only until the scripture text is on the device. The app fetches it by itself on first run; there is nothing
/// to choose. No account is involved and nothing personal is sent.
class WelcomeScreen extends StatelessWidget {
  const WelcomeScreen({super.key, required this.app});
  final AppController app;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Scaffold(
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 560),
          child: Padding(
            padding: const EdgeInsets.all(32),
            child: ListenableBuilder(
              listenable: app,
              builder: (context, _) => Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  ScripturesMark(size: 72, onDark: Theme.of(context).brightness == Brightness.dark, semanticLabel: 'Scriptura'),
                  const SizedBox(height: 16),
                  Text('Welcome', style: t.headlineMedium),
                  const SizedBox(height: 8),
                  Text(
                    'A private scripture library that works offline: read, search by meaning or exact words, and keep your own '
                    'notes. Getting ready takes a few minutes the first time.',
                    style: t.bodyLarge,
                  ),
                  const SizedBox(height: 24),
                  SetupProgress(app: app),
                  const SizedBox(height: 24),
                  Text(
                    'Every file is verified before it is used. Nothing personal is ever sent, and no account is needed.',
                    style: t.bodySmall,
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
