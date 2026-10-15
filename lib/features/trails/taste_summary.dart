import '../../data/content/catalog.dart';

String tasteSentence({required List<String> familyLabels, String? volumeName}) {
  if (familyLabels.isEmpty) return 'Like a few verses on a trail and your taste will show here.';
  final fams = familyLabels.map((l) => l.toLowerCase()).join(' and ');
  return volumeName == null ? 'You lean toward $fams.' : 'You lean toward $fams, mostly in $volumeName.';
}

List<({String name, double share})> volumeShares(List<int> verses, List<VolumeEntry> volumes) {
  if (verses.isEmpty) return const [];
  final counts = <String, int>{};
  for (final v in verses) {
    for (final vol in volumes) {
      if (v >= vol.firstVerseId && v <= vol.lastVerseId) {
        counts[vol.name] = (counts[vol.name] ?? 0) + 1;
        break;
      }
    }
  }
  final out = [for (final e in counts.entries) (name: e.key, share: e.value / verses.length)];
  out.sort((a, b) => b.share.compareTo(a.share));
  return out;
}
