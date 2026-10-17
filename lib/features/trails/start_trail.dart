import 'package:flutter/material.dart';

import '../../app_controller.dart';
import '../../data/trails/trail_models.dart';
import 'trail_screen.dart';

String _short(String s) => s.length <= 40 ? s : '${s.substring(0, 37)}...';

/// Creates a trail from a seed, remembers it as the active one and opens it.
Future<void> startTrail(
  BuildContext context,
  AppController app, {
  required TrailSeed seed,
  required String name,
  List<String> moods = const [],
  List<TrailSeed> extraSeeds = const [],
}) async {
  final trail = app.user.createTrail(name: _short(name), seed: seed, moods: moods);
  for (final s in extraSeeds) {
    app.user.addTrailSeed(trail.id, s);
  }
  await openTrail(context, app, trail);
}

Future<void> openTrail(BuildContext context, AppController app, Trail trail) async {
  app.user.setPref('active_trail', trail.id);
  await Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => TrailScreen(app: app, trail: trail)));
}
