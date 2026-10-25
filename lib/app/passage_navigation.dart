import 'package:flutter/material.dart';

import 'passage_selection.dart';

/// Shared passage shortcuts for result cards, preview and full reader.
class PassageNavigation extends StatelessWidget {
  const PassageNavigation({
    super.key,
    required this.selection,
    required this.onSelect,
    this.color,
    this.surfaceColor,
    this.controls = true,
  });
  final PassageSelection selection;
  final ValueChanged<int> onSelect;
  final Color? color;
  final Color? surfaceColor;
  final bool controls;

  @override
  Widget build(BuildContext context) {
    final ink = color ?? Theme.of(context).colorScheme.onSurface;
    final surface = surfaceColor ?? Theme.of(context).colorScheme.surface;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (selection.runs.length > 1)
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: [
                for (var i = 0; i < selection.runs.length; i++)
                  Padding(
                    padding: const EdgeInsets.only(right: 6),
                    child: Semantics(
                      label: 'Go to passage ${runLabel(selection.runs[i])}',
                      child: ChoiceChip(
                        label: Text(runLabel(selection.runs[i])),
                        labelStyle: TextStyle(color: ink),
                        // The app theme may be dark while this reading page is
                        // light. Use an opaque fill from the local surface.
                        color: WidgetStateProperty.resolveWith(
                            (states) => Color.alphaBlend(
                                  ink.withValues(
                                      alpha:
                                          states.contains(WidgetState.selected)
                                              ? 0.16
                                              : 0.04),
                                  surface,
                                )),
                        side: BorderSide(color: ink.withValues(alpha: 0.4)),
                        checkmarkColor: ink,
                        showCheckmark: true,
                        selected: selection.activeRun == i,
                        onSelected: (_) => onSelect(i),
                      ),
                    ),
                  ),
              ],
            ),
          ),
        if (controls && selection.runs.length > 1)
          Wrap(
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              IconButton(
                tooltip: 'Previous passage',
                color: ink,
                disabledColor: ink.withValues(alpha: 0.3),
                onPressed: selection.activeRun == 0
                    ? null
                    : () => onSelect(selection.activeRun - 1),
                icon: const Icon(Icons.chevron_left),
              ),
              Text(
                'Passage ${selection.activeRun + 1} of ${selection.runs.length}',
                style: TextStyle(color: ink),
              ),
              IconButton(
                tooltip: 'Next passage',
                color: ink,
                disabledColor: ink.withValues(alpha: 0.3),
                onPressed: selection.activeRun == selection.runs.length - 1
                    ? null
                    : () => onSelect(selection.activeRun + 1),
                icon: const Icon(Icons.chevron_right),
              ),
            ],
          ),
      ],
    );
  }
}
