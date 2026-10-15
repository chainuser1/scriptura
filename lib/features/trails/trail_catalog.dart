import 'dart:convert';

import 'package:flutter/services.dart' show AssetBundle, rootBundle;

class Mood {
  const Mood(this.id, this.label, this.blurb, this.genes);
  final String id, label, blurb;
  final List<({String id, double weight})> genes;
}

class Starter {
  const Starter(this.id, this.title, this.blurb, this.moodId, this.question, this.icon);
  final String id, title, blurb, moodId, question, icon;
}

/// Moods, starter trails and gene and family labels: small, editable data shipped with the app.
class TrailCatalog {
  TrailCatalog._(this.moods, this.starters, this._families, this._genes);

  final List<Mood> moods;
  final List<Starter> starters;
  final Map<String, String> _families, _genes;

  static Future<TrailCatalog>? _shared;
  static TrailCatalog? _loaded;

  /// The catalog once it has loaded, so widgets can paint it on their first frame.
  static TrailCatalog? get loaded => _loaded;

  /// Loaded once. After that every caller gets a fresh completed future, never one that belongs to another zone.
  static Future<TrailCatalog> get shared {
    final done = _loaded;
    if (done != null) return Future.value(done);
    return _shared ??= load().then((c) => _loaded = c);
  }

  static Future<TrailCatalog> load([AssetBundle? bundle]) async {
    final b = bundle ?? rootBundle;
    Future<Map<String, dynamic>> read(String p) async => jsonDecode(await b.loadString(p)) as Map<String, dynamic>;
    return TrailCatalog.fromJson(await read('assets/trail_moods.json'), await read('assets/trail_starters.json'), await read('assets/genome_labels.json'));
  }

  factory TrailCatalog.fromJson(Map<String, dynamic> moods, Map<String, dynamic> starters, Map<String, dynamic> labels) {
    return TrailCatalog._(
      [
        for (final m in (moods['moods'] as List).cast<Map>())
          Mood(m['id'] as String, m['label'] as String, m['blurb'] as String, [
            for (final g in (m['genes'] as List).cast<Map>()) (id: g['id'] as String, weight: (g['weight'] as num).toDouble()),
          ])
      ],
      [
        for (final s in (starters['starters'] as List).cast<Map>())
          Starter(s['id'] as String, s['title'] as String, s['blurb'] as String, s['mood'] as String, s['question'] as String, s['icon'] as String)
      ],
      (labels['families'] as Map).cast<String, String>(),
      (labels['genes'] as Map).cast<String, String>(),
    );
  }

  Mood? mood(String id) {
    for (final m in moods) {
      if (m.id == id) return m;
    }
    return null;
  }

  /// The engine's wire form of a mood: `[{id, weight}, ...]`; empty for an unknown id.
  List<Map<String, dynamic>> moodGenes(String id) => [for (final g in mood(id)?.genes ?? const []) {'id': g.id, 'weight': g.weight}];

  String familyLabel(String letter) => _families[letter] ?? letter;

  String geneLabel(String id) {
    final known = _genes[id];
    if (known != null) return known;
    final rest = id.contains('_') ? id.substring(id.indexOf('_') + 1) : id;
    final t = rest.replaceAll('_', ' ');
    return t.isEmpty ? id : t[0].toUpperCase() + t.substring(1);
  }
}
