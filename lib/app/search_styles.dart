/// The search mixes the engine offers, in reader's words. Weights live in the engine pack (tool/data/fusion_profiles.json);
/// this list only names them and says what each is good for. Compass is the default.
class SearchStyle {
  const SearchStyle(this.id, this.name, this.summary, {required this.needsIndex});
  final String id, name, summary;

  /// True when the mix uses the optional word-level index; without it the engine uses Lantern instead.
  final bool needsIndex;
}

const searchStyles = <SearchStyle>[
  SearchStyle('compass', 'Compass', 'Balanced. The best all-rounder and the recommended choice.', needsIndex: true),
  SearchStyle('wayfarer', 'Wayfarer', 'Leans toward the exact wording. Good for names and definitions.', needsIndex: true),
  SearchStyle('lantern', 'Lantern', 'Balanced without the word-level index. What Compass falls back to.', needsIndex: false),
  SearchStyle('chorus', 'Chorus', 'An even blend of meaning and wording. Weaker on how-to questions.', needsIndex: true),
  SearchStyle('tide', 'Tide', 'Topic and feeling over wording. Good for how you are feeling.', needsIndex: true),
  SearchStyle('feather', 'Feather', 'Smallest and fastest. Weaker on names.', needsIndex: false),
  SearchStyle('gemini', 'Gemini', 'Themes and word-by-word matching only.', needsIndex: true),
];

const kDefaultSearchStyle = 'compass';
