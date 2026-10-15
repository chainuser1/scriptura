import 'package:flutter/material.dart';

import '../../app/brand.dart';

/// Where this app comes from: the research that preceded it, told from the project's own records
/// (the Scripture Genome Project, PLAN 1 and PLAN 2). Facts only; the author's own words go in [kAuthorNote].
///
/// Set [kAuthorNote] to a sentence or two in your own voice about what moved you to start; it appears under the opening.
/// It is left empty because the project records state the design, not the personal reason.
const String kAuthorNote = '';

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
    Widget p(String s) => Padding(padding: const EdgeInsets.only(bottom: 10), child: Text(s, style: t.bodyLarge?.copyWith(height: 1.5)));
    Widget fact(String k, String v) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 4),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            SizedBox(width: 150, child: Text(k, style: t.bodyMedium?.copyWith(fontWeight: FontWeight.w700))),
            Expanded(child: Text(v, style: t.bodyMedium)),
          ]),
        );
    return Scaffold(
      appBar: AppBar(title: const Text('The story behind this app')),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 760),
          child: ListView(
            padding: const EdgeInsets.fromLTRB(24, 16, 24, 48),
            children: [
              Row(children: [
                ScripturesMark(size: 56, onDark: Theme.of(context).brightness == Brightness.dark),
                const SizedBox(width: 16),
                Expanded(child: Text('From measuring what a verse is, to finding it by what you ask', style: t.headlineSmall)),
              ]),
              const SizedBox(height: 16),
              p('This app grew out of the Scripture Genome Project by Jayson Rael Ramos, which set out to describe every verse by what '
                  'the text itself carries, so that a person who does not know the right words can still be led to the right passage. '
                  'The reader you are using is the last step of that work.'),
              if (kAuthorNote.isNotEmpty) p(kAuthorNote),
              h('1 · The genome'),
              p('The Scripture Genome Project ("Scriptures in View") gives every verse of the standard works a fingerprint: '
                  '568 scores, one for each of 568 "genes" grouped into 23 families. The families describe literary form, imagery, '
                  'emotional texture, human themes, divine reference, moral texture, voice, covenant structure, historical context, '
                  'doctrinal weight, and how a passage teaches or applies. Each gene is scored 1 to 5, from absent to defining.'),
              p('The rule was to stay tradition-neutral: score what is present in the text, with no denominational interpretation '
                  'and no outside commentary. Large language models did the scoring, one family at a time, and a verse was kept only when '
                  'all 568 genes were present.'),
              fact('Corpus', '41,995 verses: Bible 31,102, Book of Mormon 6,604, Doctrine and Covenants 3,654, Pearl of Great Price 635'),
              fact('Schema', 'version 5.0: 495 locked genes (families A to U) plus 73 added in July 2026 (families V and W)'),
              h('2 · The questions'),
              p('A fingerprint on its own does not help someone who arrives with a question. So a set of 47,400 study questions was '
                  'assembled in eight languages, each mapped to the verses that answer it (232,310 links, all marked reviewed in the '
                  'project records). They span doctrine, '
                  'discipleship, pastoral care and the Restoration, and they became the training signal that connects how people ask '
                  'to what the scriptures contain.'),
              h('3 · The model'),
              p('A small trained network sits on top of the multilingual BGE-M3 encoder. It takes the meaning of a question and predicts '
                  'which genes a good answer would light up (a 1024 to 4096 to 568 head, pinned to an exact base-model revision so '
                  'results are reproducible). A question and a verse can then be compared in the same 568-dimensional space, '
                  'even when they share no words.'),
              h('4 · This app'),
              p('The research became a reader that works offline, on your own device. A search combines four signals and names them: '
                  'Echo (what the passage means, by embedding), Spark (the exact words), Thread (word-by-word matching) and Root '
                  '(the genome). Compass, the default, leans on Root; other mixes are available for different questions. '
                  'A native engine written in Rust runs the same model on Windows and on Android phones, with no account and no server.'),
              fact('What it adds', 'reading with the standard works in five languages, search by meaning, exact phrases, similar verses, '
                  'people and places, study questions for a passage, and your own notes and highlights'),
              fact('Where it runs', 'on your device; scripture text and search data are downloaded once and checked before use'),
              h('5 · What it does not claim'),
              p('The genome scores and the question links were produced with large language models and have not been independently '
                  'verified verse by verse; they are measurements, not doctrine. Only about 5,000 of the 41,995 verses are direct answer targets for the question set, so results for '
                  'quieter parts of the canon rely more on meaning and wording than on curated links. People and place recognition '
                  'is built to prefer being right over being complete. Where the app is unsure it shows what it understood and lets you choose.'),
              h('Timeline from the project records'),
              fact('30 May 2026', 'plan for the genome corpus written'),
              fact('4 July 2026', 'schema v5.0: 568 genes, 23 families'),
              fact('July to October', 'scoring, question writing and review, encoder head training and selection'),
              fact('8 October 2026', 'research archived; three application databases separated from the code'),
              fact('11 October 2026', 'model head prepared for public release'),
              fact('October 2026', 'this reader: offline engine, Windows and Android apps'),
              h('Text and licences'),
              p('The Bible text is in the public domain. The licence and copyright of the Book of Mormon, Doctrine and Covenants and '
                  'Pearl of Great Price belong to The Church of Jesus Christ of Latter-day Saints (© Intellectual Reserve, Inc.). Their use '
                  'is subject to the Church\'s terms and is not covered by the licence of this app. See Settings, Sources and licences.'),
              h('Credits'),
              p('Published by Scriptura Labs under the MIT licence. Author and designer: Jayson Rael Ramos. Base model BGE-M3 by BAAI (MIT licence). Interface type Inter and scripture type '
                  'Source Serif 4 (with Literata and Atkinson Hyperlegible as optional reading faces), all under the SIL Open Font License.'),
            ],
          ),
        ),
      ),
    );
  }
}
