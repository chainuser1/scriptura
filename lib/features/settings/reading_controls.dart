import 'package:flutter/material.dart';

import '../../app/looks.dart';
import '../../app/theme.dart';
import '../../data/user/user_store.dart';

const _sampleText = 'In the beginning God created the heaven and the earth.';

/// The named looks as a swipeable row of small live previews. One tap applies a look; "Custom" shows when the controls
/// no longer match any look.
class LookGallery extends StatelessWidget {
  const LookGallery({super.key, required this.user, this.wrapWhenWide = false});
  final UserStore user;

  /// On a wide surface show every look at once (a mouse has no swipe); a phone or a narrow panel scrolls sideways.
  final bool wrapWhenWide;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;
    return ListenableBuilder(
      listenable: user,
      builder: (context, _) {
        final current = lookOf(user);
        Widget card(ReadingLook look) {
          final p = ReadingPrefs.resolve(look.values);
          final selected = current?.id == look.id;
          return Semantics(
            button: true,
            selected: selected,
            label: '${look.name} look. ${look.blurb}',
            child: InkWell(
              borderRadius: BorderRadius.circular(12),
              onTap: () => applyLook(user, look),
              child: Container(
                width: 156,
                height: 148,
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: p.theme.background,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: selected ? scheme.primary : p.theme.text.withValues(alpha: 0.25), width: selected ? 2.5 : 1),
                ),
                child: ExcludeSemantics(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Row(children: [
                      Expanded(child: Text(look.name, maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(color: p.theme.text, fontWeight: FontWeight.w700, fontSize: 14))),
                      if (selected) Icon(Icons.check_circle, size: 18, color: scheme.primary),
                    ]),
                    const SizedBox(height: 6),
                    Expanded(
                      child: ClipRect(
                        child: Text(
                          _sampleText,
                          overflow: TextOverflow.fade,
                          style: p.style(color: p.theme.text, extraScale: 0.62).copyWith(height: p.spacing.height),
                        ),
                      ),
                    ),
                  ]),
                ),
              ),
            ),
          );
        }

        return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          LayoutBuilder(builder: (context, box) {
            if (wrapWhenWide && box.maxWidth >= 600) {
              return Wrap(spacing: 10, runSpacing: 10, children: [for (final l in looks) card(l)]);
            }
            return SizedBox(
              height: 148,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                itemCount: looks.length,
                separatorBuilder: (_, __) => const SizedBox(width: 10),
                itemBuilder: (context, i) => card(looks[i]),
              ),
            );
          }),
          const SizedBox(height: 8),
          Text(
            current == null ? 'Custom: you have adjusted the controls below.' : current.blurb,
            style: t.bodySmall,
          ),
        ]);
      },
    );
  }
}

/// The individual reading controls. [compact] keeps the four most used (colour, typeface, size, spacing) for the reader's
/// quick menu; the full set lives in Settings.
class ReadingControls extends StatelessWidget {
  const ReadingControls({super.key, required this.user, this.compact = false});
  final UserStore user;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;
    Widget label(String s) => Padding(padding: const EdgeInsets.only(top: 16, bottom: 8), child: Semantics(header: true, child: Text(s, style: t.labelLarge)));
    return ListenableBuilder(
      listenable: user,
      builder: (context, _) {
        final p = ReadingPrefs.of(user, now: DateTime(2000, 1, 1, 12)); // the controls show what is chosen, not the night override
        return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          label('Page colour: ${p.theme.label}'),
          Wrap(spacing: 10, runSpacing: 10, children: [
            for (final th in ReadingTheme.values)
              Semantics(
                button: true,
                selected: p.theme == th,
                label: '${th.label} page colour',
                child: Tooltip(
                  message: th.label,
                  child: InkWell(
                    customBorder: const CircleBorder(),
                    onTap: () => user.setPref('reading_theme', th.name),
                    child: Container(
                      width: 44,
                      height: 44,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        color: th.background,
                        shape: BoxShape.circle,
                        border: Border.all(color: p.theme == th ? scheme.primary : th.text.withValues(alpha: 0.35), width: p.theme == th ? 3 : 1),
                      ),
                      child: Text('A', style: TextStyle(color: th.text, fontWeight: FontWeight.w700, fontSize: 15)),
                    ),
                  ),
                ),
              ),
          ]),
          label('Typeface'),
          Wrap(spacing: 8, runSpacing: 8, children: [
            for (final f in ReadingFont.values)
              ChoiceChip(
                label: Text(f.label, style: TextStyle(fontFamily: f.family, fontFamilyFallback: f.fallback)),
                selected: p.font == f,
                onSelected: (_) => user.setPref('reading_font', f.name),
              ),
          ]),
          label('Text size'),
          Row(children: [
            Icon(Icons.text_fields, size: 16, color: scheme.onSurfaceVariant),
            Expanded(
              child: Slider(
                value: p.scale,
                min: 0.8,
                max: 1.8,
                divisions: 10,
                label: '${(p.scale * 100).round()}%',
                semanticFormatterCallback: (v) => '${(v * 100).round()} percent',
                onChanged: (v) => user.setPref('text_scale', v.toStringAsFixed(2)),
              ),
            ),
            Icon(Icons.text_fields, size: 26, color: scheme.onSurfaceVariant),
          ]),
          label('Line spacing'),
          _oneLine(SegmentedButton<LineSpacing>(
            showSelectedIcon: false,
            segments: [for (final s in LineSpacing.values) ButtonSegment(value: s, label: Text(s.label))],
            selected: {p.spacing},
            onSelectionChanged: (s) => user.setPref('line_spacing', s.first.name),
          )),
          if (!compact) ...[
            label('Line width'),
            _oneLine(SegmentedButton<int>(
              showSelectedIcon: false,
              segments: const [ButtonSegment(value: 0, label: Text('Narrow')), ButtonSegment(value: 1, label: Text('Medium')), ButtonSegment(value: 2, label: Text('Wide'))],
              selected: {p.width},
              onSelectionChanged: (s) => user.setPref('reading_width', '${s.first}'),
            )),
            label('Verse numbers'),
            _oneLine(SegmentedButton<VerseNumbers>(
              showSelectedIcon: false,
              segments: [for (final n in VerseNumbers.values) ButtonSegment(value: n, label: Text(n.label))],
              selected: {p.numbers},
              onSelectionChanged: (s) => user.setPref('verse_numbers', s.first.name),
            )),
            label('Layout'),
            _oneLine(SegmentedButton<VerseLayout>(
              showSelectedIcon: false,
              segments: [for (final l in VerseLayout.values) ButtonSegment(value: l, label: Text(l.label))],
              selected: {p.layout},
              onSelectionChanged: (s) => user.setPref('verse_layout', s.first.name),
            )),
            const SizedBox(height: 8),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Dim the page after dark'),
              subtitle: const Text('Uses the Night colours from 7 pm to 6 am, by the clock'),
              value: p.autoNight,
              onChanged: (on) => user.setPref('auto_night', on ? '1' : '0'),
            ),
          ],
        ]);
      },
    );
  }
}

/// A line of scripture in the current look, for a live preview under the controls.
class ReadingPreview extends StatelessWidget {
  const ReadingPreview({super.key, required this.user});
  final UserStore user;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: user,
      builder: (context, _) {
        final p = ReadingPrefs.of(user);
        return Container(
          margin: const EdgeInsets.only(top: 16),
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(color: p.theme.background, borderRadius: BorderRadius.circular(8), border: Border.all(color: p.theme.text.withValues(alpha: 0.2))),
          child: Text(_sampleText, style: p.style(color: p.theme.text)),
        );
      },
    );
  }
}

/// A row of choices keeps its words whole: on a narrow screen with a large font it scrolls sideways instead of breaking
/// "Comfortable" across lines.
Widget _oneLine(Widget choices) => SingleChildScrollView(scrollDirection: Axis.horizontal, child: choices);
