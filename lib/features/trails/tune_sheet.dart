import 'package:flutter/material.dart';

import '../../app/theme.dart';
import 'trail_controller.dart';

const _volumes = <(String, String)>[
  ('all', 'Across the canon'),
  ('ot', 'Old Testament'),
  ('nt', 'New Testament'),
  ('bible', 'Bible'),
  ('bom', 'Book of Mormon'),
  ('dc', 'Doctrine and Covenants'),
  ('pgp', 'Pearl of Great Price'),
];

/// Mood, volume, focus and mood strength. Changes apply at once; the card on screen stays.
Future<void> showTune(BuildContext context, TrailController c, {required VoidCallback onAddVariety}) {
  final wide = MediaQuery.sizeOf(context).width >= kWideBreakpoint;
  Widget body(BuildContext ctx) => ListenableBuilder(listenable: c, builder: (ctx, _) => _TuneBody(controller: c, onAddVariety: onAddVariety));
  if (wide) {
    return showDialog<void>(
      context: context,
      builder: (ctx) => Dialog(alignment: Alignment.topRight, insetPadding: const EdgeInsets.fromLTRB(24, 64, 24, 24), child: SizedBox(width: 420, child: body(ctx))),
    );
  }
  return showModalBottomSheet<void>(context: context, isScrollControlled: true, showDragHandle: true, builder: body);
}

class _TuneBody extends StatelessWidget {
  const _TuneBody({required this.controller, required this.onAddVariety});
  final TrailController controller;
  final VoidCallback onAddVariety;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final trail = controller.trail;
    final catalog = controller.catalog;
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(20, 4, 20, 24),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Semantics(header: true, child: Text('Tune this trail', style: t.titleMedium)),
        const SizedBox(height: 16),
        Text('Mood (up to two)', style: t.labelLarge),
        const SizedBox(height: 8),
        Wrap(spacing: 8, runSpacing: 8, children: [
          for (final m in catalog.moods)
            Tooltip(
              message: m.blurb,
              child: FilterChip(
                label: Text(m.label),
                selected: trail.moods.contains(m.id),
                onSelected: (on) {
                  final next = [...trail.moods];
                  if (on) {
                    if (next.length >= 2) next.removeAt(0);
                    next.add(m.id);
                  } else {
                    next.remove(m.id);
                  }
                  controller.tune(moods: next);
                },
              ),
            ),
        ]),
        if (trail.moods.isNotEmpty) ...[
          const SizedBox(height: 16),
          Text('Mood strength', style: t.labelLarge),
          _LiveSlider(value: trail.moodStrength, onCommit: (v) => controller.tune(moodStrength: v)),
        ],
        const SizedBox(height: 16),
        Text('Where from', style: t.labelLarge),
        const SizedBox(height: 8),
        Wrap(spacing: 8, runSpacing: 8, children: [
          for (final v in _volumes)
            ChoiceChip(label: Text(v.$2), selected: trail.volume == v.$1, onSelected: (_) => controller.tune(volume: v.$1)),
        ]),
        const SizedBox(height: 16),
        Text('How far to wander', style: t.labelLarge),
        Row(children: [
          const Text('Stay close'),
          Expanded(child: _LiveSlider(value: trail.focus, onCommit: (v) => controller.tune(focus: v))),
          const Text('Wander'),
        ]),
        const SizedBox(height: 8),
        OutlinedButton.icon(onPressed: onAddVariety, icon: const Icon(Icons.add), label: const Text('Add variety')),
      ]),
    );
  }
}

/// A slider that follows the finger and writes once, when the finger lifts.
class _LiveSlider extends StatefulWidget {
  const _LiveSlider({required this.value, required this.onCommit});
  final double value;
  final ValueChanged<double> onCommit;

  @override
  State<_LiveSlider> createState() => _LiveSliderState();
}

class _LiveSliderState extends State<_LiveSlider> {
  double? _drag;

  @override
  Widget build(BuildContext context) {
    final v = _drag ?? widget.value;
    return Slider(
      value: v,
      divisions: 10,
      label: '${(v * 100).round()}%',
      onChanged: (x) => setState(() => _drag = x),
      onChangeEnd: (x) {
        setState(() => _drag = null);
        widget.onCommit(x);
      },
    );
  }
}
