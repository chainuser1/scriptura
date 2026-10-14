import 'package:flutter/material.dart';

import '../../app/guide_content.dart';
import '../../app/nav_state.dart';
import '../../app_controller.dart';

/// A calm, neutral orientation: what is here, how to ask, how to read. No prior knowledge assumed.
class GuideScreen extends StatelessWidget {
  const GuideScreen({super.key, required this.app});
  final AppController app;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    Widget section(String title, List<Widget> children) => Padding(
          padding: const EdgeInsets.only(bottom: 28),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Semantics(header: true, child: Text(title, style: t.titleLarge)),
            const SizedBox(height: 10),
            ...children,
          ]),
        );
    return Scaffold(
      appBar: AppBar(title: const Text('Start here')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 760),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                section('What this is', [
                  Text(
                    'A private library of scripture that works without an internet connection. You can read it, search it by '
                    'meaning or by exact words, and keep your own bookmarks, highlights and notes. Nothing you do leaves this computer.',
                    style: t.bodyLarge,
                  ),
                ]),
                section('What is in the library', [
                  for (final v in volumeNotes)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 14),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text(v.title, style: t.titleMedium),
                        const SizedBox(height: 2),
                        Text(v.summary),
                        const SizedBox(height: 2),
                        Text(v.heldBy, style: t.bodySmall),
                      ]),
                    ),
                ]),
                section('Asking questions', [
                  const Text(
                    'Type a question the way you would ask a person: “How do I forgive someone?”, “What is grace?”, '
                    '“Who was Abinadi?”. The app finds the passages that speak most directly to it and shows you what it understood. '
                    'It does not write answers of its own: it points you to the scripture itself, so you can read it in context.',
                  ),
                  const SizedBox(height: 10),
                  Wrap(spacing: 8, runSpacing: 8, children: [
                    for (final q in starterQuestions.take(4))
                      ActionChip(
                        label: Text(q),
                        onPressed: () {
                          Navigator.of(context).pop();
                          app.nav.ask(q);
                        },
                      ),
                  ]),
                ]),
                section('Other ways to search', [
                  const Text('• A reference such as “John 3:16”, “Alma 32”, or “Salmos 23” jumps straight to the passage.'),
                  const SizedBox(height: 4),
                  const Text('• “Exact phrase” finds verses containing those words in that order, and tells you how many there are.'),
                  const SizedBox(height: 4),
                  const Text('• “Similar verses” on any verse finds passages with a related message.'),
                  const SizedBox(height: 4),
                  const Text('• Ctrl+K opens a command bar from anywhere.'),
                ]),
                section('Reading', [
                  const Text(
                    'Open any verse’s menu (click it, or right-click) to copy it with its reference, bookmark it, highlight it in '
                    'a colour, or add a note. Settings lets you change the text size, the reading theme and the language, and show a '
                    'second language beside the first.',
                  ),
                ]),
                Center(
                  child: FilledButton(
                    onPressed: () {
                      Navigator.of(context).pop();
                      app.nav.go(Dest.read);
                    },
                    child: const Text('Start reading'),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
