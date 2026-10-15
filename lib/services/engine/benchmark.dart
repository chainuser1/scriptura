import 'dart:convert';
import 'dart:io';

import 'search_models.dart';
import 'search_service.dart';

/// On-device latency run for the E3 gates: cold first query, then warm queries across modes. The result is plain JSON
/// so it can be read from the screen, from `adb logcat`, or from a file the caller writes.
const benchmarkQueries = <String>[
  'What is faith?',
  'faith',
  'Who is Captain Moroni?',
  'How do I overcome fear?',
  'What does the Bible teach about forgiveness?',
  'ask and ye shall receive',
  'I feel anxious and afraid about the future',
  'Faith vs knowledge',
  'In the beginning God created the heavens and the earth',
  '¿Qué dice la Biblia sobre el amor al prójimo?',
  'Ano ang sinasabi ng kasulatan tungkol sa pagpapakumbaba?',
  'Who was Alma the Younger?',
  'What are the Ten Commandments?',
  'love your enemies',
  'the purpose of life',
  'baptism of the Holy Ghost',
];

double _pct(List<double> sorted, double p) => sorted.isEmpty ? 0 : sorted[((sorted.length - 1) * p).round()];

Future<Map<String, dynamic>> runBenchmark(SearchService service, {int rounds = 3, String? profile}) async {
  final cold = <String, dynamic>{};
  final sw = Stopwatch()..start();
  final first = await service.search(SearchRequest.semantic(benchmarkQueries.first, profile: profile));
  cold['first_query_ms'] = sw.elapsedMilliseconds;
  cold['first_query_engine_ms'] = first.totalMs;
  final totals = <double>[], encodes = <double>[], searches = <double>[];
  var peakRss = ProcessInfo.currentRss;
  for (var r = 0; r < rounds; r++) {
    for (final q in benchmarkQueries) {
      final t = Stopwatch()..start();
      final resp = await service.search(SearchRequest.semantic(q, profile: profile));
      totals.add(t.elapsedMicroseconds / 1000);
      encodes.add(resp.encodeMs ?? 0);
      searches.add(resp.searchMs ?? 0);
      if (ProcessInfo.currentRss > peakRss) peakRss = ProcessInfo.currentRss;
    }
  }
  final sorted = [...totals]..sort();
  final extras = <String, dynamic>{};
  final p = Stopwatch()..start();
  await service.search(SearchRequest.phrase('the Lord is my shepherd'));
  extras['phrase_ms'] = p.elapsedMilliseconds;
  p.reset();
  await service.search(SearchRequest.similar(26137));
  extras['similar_ms'] = p.elapsedMilliseconds;
  p.reset();
  await service.search(SearchRequest.search('John 3:16'));
  extras['reference_ms'] = p.elapsedMilliseconds;
  final tn = <double>[];
  for (var i = 0; i < 15; i++) {
    final w = Stopwatch()..start();
    await service.search(SearchRequest.raw('trail_next', {
      'k': 10, 'step': 0, 'seed': {'verse_id': 26137}, 'events': <Object>[], 'recent': <int>[], 'moods': <Object>[],
      'mood_strength': 0.5, 'focus': 0.5, 'filter': null, 'language': 'english',
    }));
    tn.add(w.elapsedMicroseconds / 1000);
  }
  extras['trail_next_ms'] = _pct([...tn]..sort(), 0.5);
  return {
    'platform': Platform.operatingSystem,
    'os_version': Platform.operatingSystemVersion,
    'processors': Platform.numberOfProcessors,
    'profile': profile ?? 'default',
    'has_colbert_pack': service.hasColbertPack,
    'queries': benchmarkQueries.length,
    'rounds': rounds,
    'cold': cold,
    'warm_total_ms': {'median': _pct(sorted, 0.5), 'p95': _pct(sorted, 0.95), 'max': sorted.last, 'min': sorted.first},
    'warm_encode_ms_median': _pct([...encodes]..sort(), 0.5),
    'warm_search_ms_median': _pct([...searches]..sort(), 0.5),
    'rss_mb_peak': (peakRss / (1 << 20)).round(),
    ...extras,
  };
}

String benchmarkReport(Map<String, dynamic> r) => const JsonEncoder.withIndent('  ').convert(r);
