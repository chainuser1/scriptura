// Plain, neutral wording for people who are new to these books. Each description says what a volume is and who holds
// it; none of it argues for or against any tradition.

class VolumeNote {
  const VolumeNote(this.key, this.title, this.summary, this.heldBy);
  final String key, title, summary, heldBy;
}

const volumeNotes = <VolumeNote>[
  VolumeNote(
    'ot',
    'Old Testament',
    'The older part of the Christian Bible: 39 books of law, history, poetry, wisdom and prophecy, from creation '
        'through the prophets of ancient Israel. Stories such as Noah, Moses and David are here.',
    'Shared by Jews (who call it the Hebrew Bible or Tanakh) and Christians.',
  ),
  VolumeNote(
    'nt',
    'New Testament',
    'The life and teaching of Jesus Christ in four Gospels, the story of the first Christians, letters from apostles '
        'such as Paul, and the Revelation of John.',
    'Christian scripture.',
  ),
  VolumeNote(
    'bom',
    'Book of Mormon',
    'A volume that presents itself as the record of ancient peoples in the Americas and of Jesus Christ appearing '
        'among them. Its books are named for their prophets and writers, such as Nephi, Alma and Moroni.',
    'Held as scripture by The Church of Jesus Christ of Latter-day Saints and some other Restoration churches.',
  ),
  VolumeNote(
    'dc',
    'Doctrine and Covenants',
    'Revelations and instructions given in the 1800s, mostly through Joseph Smith, about doctrine, the organisation '
        'of the Church and personal conduct.',
    'Held as scripture by The Church of Jesus Christ of Latter-day Saints and some other Restoration churches.',
  ),
  VolumeNote(
    'pgp',
    'Pearl of Great Price',
    'A short collection: writings attributed to Moses and Abraham, a further account of Matthew 24, a history of '
        'Joseph Smith, and the Articles of Faith.',
    'Held as scripture by The Church of Jesus Christ of Latter-day Saints.',
  ),
];

/// Questions people commonly bring. Each runs as an ordinary search, so the results are the app's honest answer.
const starterQuestions = <String>[
  'Who is Jesus Christ?',
  'What is faith?',
  'How do I pray?',
  'How can I find peace?',
  'What happens after we die?',
  'Why do bad things happen to good people?',
  'How do I forgive someone?',
  'What is the purpose of life?',
];

class VerseRef {
  const VerseRef(this.book, this.chapter, this.verse);
  final String book;
  final int chapter, verse;
}

/// Widely quoted passages for the daily verse; the day of the year picks one.
const dailyVerses = <VerseRef>[
  VerseRef('John', 3, 16),
  VerseRef('Psalms', 23, 1),
  VerseRef('Proverbs', 3, 5),
  VerseRef('Isaiah', 41, 10),
  VerseRef('Philippians', 4, 13),
  VerseRef('Matthew', 11, 28),
  VerseRef('Romans', 8, 28),
  VerseRef('Joshua', 1, 9),
  VerseRef('Jeremiah', 29, 11),
  VerseRef('Micah', 6, 8),
  VerseRef('Matthew', 5, 9),
  VerseRef('1 Corinthians', 13, 4),
  VerseRef('James', 1, 5),
  VerseRef('Psalms', 46, 10),
  VerseRef('Ecclesiastes', 3, 1),
  VerseRef('Galatians', 5, 22),
  VerseRef('2 Nephi', 2, 25),
  VerseRef('Alma', 32, 21),
  VerseRef('Moroni', 10, 4),
  VerseRef('Mosiah', 2, 17),
  VerseRef('Ether', 12, 27),
  VerseRef('Doctrine and Covenants', 6, 36),
  VerseRef('Doctrine and Covenants', 18, 10),
  VerseRef('Moses', 1, 39),
  VerseRef('Psalms', 119, 105),
  VerseRef('Hebrews', 11, 1),
  VerseRef('Matthew', 6, 33),
  VerseRef('Luke', 6, 31),
  VerseRef('Psalms', 121, 1),
  VerseRef('Isaiah', 40, 31),
];
