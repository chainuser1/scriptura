import 'package:flutter/material.dart';

import '../../app/brand.dart';

/// Our story: why Scriptura exists, told for readers in plain words (the same story as the Scriptura Labs website).
/// No technical detail here; the research records stay in the project, the licences in Settings, Sources and licences.
///
/// Set [kAuthorNote] to a sentence or two in your own voice about what moved you to start; it appears as the founder's note.
const String kAuthorNote = 'So many times I knew the scriptures held an answer, but I could not find the words to search for it. '
    'I started the Scripture Genome Project because I believe no one should have to know the right words to find the right '
    'verse. My part was to build a better path to them, and to keep it free for everyone.';

class AboutScreen extends StatelessWidget {
  const AboutScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;
    Widget h(String s) => Padding(
          padding: const EdgeInsets.only(top: 32, bottom: 8),
          child: Semantics(header: true, child: Text(s.toUpperCase(), style: t.labelLarge?.copyWith(fontWeight: FontWeight.w700, letterSpacing: 1.2, color: scheme.primary))),
        );
    Widget p(String s) => Padding(padding: const EdgeInsets.only(bottom: 12), child: Text(s, style: t.bodyLarge?.copyWith(height: 1.55)));
    Widget point(String title, String s) => Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: Text.rich(TextSpan(children: [
            TextSpan(text: '$title  ', style: t.bodyLarge?.copyWith(fontWeight: FontWeight.w700, height: 1.55)),
            TextSpan(text: s, style: t.bodyLarge?.copyWith(height: 1.55)),
          ])),
        );
    return Scaffold(
      appBar: AppBar(title: const Text('Our story')),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 760),
          child: ListView(
            padding: const EdgeInsets.fromLTRB(24, 16, 24, 48),
            children: [
              Row(children: [
                ScripturesMark(size: 56, onDark: Theme.of(context).brightness == Brightness.dark),
                const SizedBox(width: 16),
                Expanded(child: Text("Finding the verse you need, even when you don't know the words", style: t.headlineSmall)),
              ]),
              const SizedBox(height: 20),
              p('Most of us know the feeling. You are carrying something heavy: worry, grief, a hard choice, a question you '
                  "can't put down. You know the scriptures speak to it. But where?"),
              p('If you remember the right words, a search can help. Type "peace" and you find verses with "peace" in them. '
                  "But the verse you need may never use that word. You may only know how you feel, not how the passage is written."),
              p("For a long time, finding the right passage depended on knowing the right words, or on knowing someone who did. "
                  "We believed it shouldn't."),
              h('Words are not the whole story'),
              p('A verse is more than its words. It carries a feeling and speaks in its own voice. It may hold a promise, a warning '
                  'or a comfort. Two verses can share none of the same words and still say the same thing to your heart.'),
              p('We wanted a way to find scripture by what it carries, not only by what it says.'),
              h('The Scripture Genome Project'),
              p('So we began the Scripture Genome Project. The idea was simple to say and big to do: describe every verse by what is '
                  'truly in the text, like a fingerprint for each one.'),
              p('We described all 41,995 verses of the Holy Bible, the Book of Mormon, the Doctrine and Covenants and the Pearl of '
                  'Great Price, one by one: their feeling, their themes, their voice and their place in the story.'),
              p('We kept one rule from the start: describe what is in the text, and nothing more. No opinions added, and no reading '
                  'from any one tradition. The scriptures speak for themselves.'),
              h('From research to a reader'),
              p('A description on its own is only a map. People need a way to ask a real question and be led to the right place. '
                  'That is why we made Scriptura.'),
              p('Scriptura is powered by the Scripture Genome Project. Ask in your own words, like "How can I find peace?" or '
                  '"I feel alone", and Scriptura finds the verses that speak to it, even when they use different words, and even in '
                  'a book you would not have thought to open.'),
              h('How we made it'),
              point('Free.', 'Scriptura costs nothing, and it will never be sold.'),
              point('Private.', 'There is no account and no tracking. Your questions, notes and highlights stay on this device.'),
              point('Offline.', 'Once it is set up, it works anywhere, even without internet.'),
              point('Fair.', 'Every book of scripture gets a fair chance to answer you, so no volume crowds out the others.'),
              point('In context.', 'Scriptura is a reading aid, not a teacher of doctrine. Every verse is one tap from its full '
                  'chapter, so you can always read it where it stands.'),
              h('Our hope'),
              p("You don't need to know where a verse is to find it, and you don't need the exact words. You only need your "
                  'question. Our hope is simple: when you need a verse, you find it.'),
              if (kAuthorNote.isNotEmpty) ...[
                h('A note from the founder'),
                p(kAuthorNote),
              ],
              p('— Jayson Rael Ramos, Founder, Scriptura Labs'),
              h('Text and licences'),
              p('The Bible text is in the public domain. The licence and copyright of the Book of Mormon, the Doctrine and Covenants '
                  'and the Pearl of Great Price belong to The Church of Jesus Christ of Latter-day Saints (© Intellectual Reserve, '
                  "Inc.), and their use follows the Church's terms. Scriptura is free of charge and is not an official app of any "
                  'church. Details are in Settings, Sources and licences.'),
              h('Credits'),
              p('Made by Scriptura Labs, scriptura.space (MIT licence). Founder and designer: Jayson Rael Ramos. Search uses BGE-M3 by BAAI '
                  '(MIT licence). Typefaces: Inter, Source Serif 4, Literata and Atkinson Hyperlegible (SIL Open Font License).'),
            ],
          ),
        ),
      ),
    );
  }
}
