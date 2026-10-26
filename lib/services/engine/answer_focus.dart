import 'dart:convert';

/// Answer focus: the device trial selects a model; the reader selects how many
/// search results it checks. Real timings can disable Automatic on a slow device.

/// The reader's setting (Settings › Advanced). Stored as pref `answer_focus`.
enum FocusMode {
  automatic,
  on,
  off;

  static FocusMode parse(String? s) => values.firstWhere((m) => m.name == s, orElse: () => FocusMode.automatic);
}

/// Which pack: `answer-focus-int8-v1` (CPU) or `answer-focus-fp16-v1` (graphics chip).
enum FocusVariant { none, int8, fp16 }

/// Which model: Ezra (always available), Apollos, Priscilla, or Aquila. Ezra is also the "nothing chosen yet" placeholder.
enum FocusModel { ezra, apollos, priscilla, aquila }

/// Result limits offered in Settings, shared by every model.
const focusCandidateCounts = [10, 15, 30, 60, 100];
const defaultFocusLimit = 60;

/// Model allowances at the default 60-result limit. [focusBudgetMs] scales these
/// proportionally for the selected count, retaining the existing device boundary.
const kFocusBudgetMs = 9000.0;

/// CPU Answer focus time per candidate relative to the device trial (measured on the reference laptop: trial 1839 ms,
/// 10 candidates 1270 ms).
const _cpuFactor = 0.069;

/// The larger models retain 40s per ten results: 240s at the default limit.
/// This is a ceiling, not a fixed wait.
const kApollosBudgetMs = 240000.0;

/// Apollos's own CPU cost-per-candidate constant, measured on a real Android phone (2026-10-19):
/// device trial cpu_ms 1238/1295 (avg 1267), k=10 completed in 12846/12342 ms (avg 12594) -- a real,
/// unforced `session.run()` time, not a timeout. `12594 / (1267 * 10)` ~= 0.994. This replaces an
/// earlier UNMEASURED placeholder (`_cpuFactor * 2`) that assumed Apollos cost about the same per
/// candidate as Ezra's much smaller model -- it does not: this is ~14x Ezra's `_cpuFactor`.
/// Automatic also checks real search timings, as it does for Ezra.
const _apollosCpuFactor = 0.994;

/// Priscilla's own CPU cost-per-candidate constant, cross-calibrated against Apollos's real
/// `_apollosCpuFactor` (2026-10-25): both models' real `Focus::score` timed on identical Windows desktop
/// hardware, against their real, production-installed packs (k=10, 3 runs). Apollos: 394/451/435 ms per
/// candidate (avg ~427). Priscilla: 51.6/68.2/54.5 ms per candidate (avg ~58) -- about 1/7th Apollos's real
/// cost, not comparable to it at all, despite sharing its time allowance. Ratio (priscilla_ms/apollos_ms)
/// per run: 0.1308/0.1511/0.1254, avg ~0.135; `_apollosCpuFactor * 0.135` ~= 0.134. This replaces an earlier
/// UNMEASURED placeholder that reused Ezra's own `_cpuFactor` (0.069) -- a real phone-class `device_trial`
/// baseline was not available locally to measure this against Apollos's own original method directly, but
/// this cross-calibration ties it to Apollos's real number rather than guessing again. Still not a
/// phone-class measurement (see `_apollosCpuFactor`'s own); replace once that becomes available.
const _priscillaCpuFactor = 0.134;

/// UNMEASURED placeholder, deliberately set equal to Apollos's own real, measured `_apollosCpuFactor`
/// (0.994) rather than a fresh guess: Aquila, like Apollos, is a real ~400m-parameter-class model (not
/// small like Ezra), and its shipped pack uses the same weight-only quantization approach Priscilla's own
/// pack uses. This is the most defensible starting point available without a real Aquila-specific
/// measurement -- strictly more honest than Priscilla's own original mistake (borrowing Ezra's much
/// smaller factor for a much larger model). Replace once real device data for Aquila specifically exists,
/// same as `_priscillaCpuFactor` itself still needs.
const _aquilaCpuFactor = _apollosCpuFactor;

class FocusChoice {
  const FocusChoice(this.model, this.variant, this.k, this.predictedMs);
  final FocusModel model;
  final FocusVariant variant;
  final int k;
  final double predictedMs;

  static const none = FocusChoice(FocusModel.ezra, FocusVariant.none, 0, 0);

  String toJson() => jsonEncode({'model': model.name, 'variant': variant.name, 'k': k, 'predicted_ms': predictedMs});

  static FocusChoice? fromJson(String? s) {
    try {
      final m = jsonDecode(s!) as Map<String, dynamic>;
      // Saved before the model field existed: those were Ezra.
      final model = m['model'] == null ? FocusModel.ezra : FocusModel.values.byName(m['model'] as String);
      final variant = FocusVariant.values.byName(m['variant'] as String);
      if (variant == FocusVariant.none) return FocusChoice.none;
      final savedK = m['k'] as int;
      return FocusChoice(model, variant, savedK, (m['predicted_ms'] as num).toDouble());
    } catch (_) {
      return null;
    }
  }

  /// Changing the pool does not change or reload the installed model.
  FocusChoice withLimit(int limit) {
    if (variant == FocusVariant.none || k == limit) return this;
    return FocusChoice(model, variant, limit, k > 0 ? predictedMs * limit / k : predictedMs);
  }

  @override
  bool operator ==(Object other) =>
      other is FocusChoice && other.model == model && other.variant == variant && other.k == k && other.predictedMs == predictedMs;
  @override
  int get hashCode => Object.hash(model, variant, k, predictedMs);
  @override
  String toString() => 'FocusChoice(${model.name}, ${variant.name}, $k, ${predictedMs.round()} ms)';
}

/// Select a model for the requested limit. The budget scales with the count,
/// so asking for more passages does not itself trigger a fallback. A working
/// GPU is offered only for Ezra; the other profiles currently use CPU packs.
/// [force] preserves an accepted slower-model override, except when Off.
FocusChoice choose({
  required double cpuMs,
  required bool gpu,
  required FocusMode mode,
  required FocusModel preferred,
  bool force = false,
  int limit = defaultFocusLimit,
}) {
  if (!focusCandidateCounts.contains(limit)) throw ArgumentError.value(limit, 'limit');
  if (mode == FocusMode.off) return FocusChoice.none;
  if (preferred != FocusModel.ezra) {
    final factor = switch (preferred) {
      FocusModel.apollos => _apollosCpuFactor,
      FocusModel.priscilla => _priscillaCpuFactor,
      FocusModel.aquila => _aquilaCpuFactor,
      FocusModel.ezra => _cpuFactor,
    };
    final ms = cpuMs * factor * limit;
    if (force || ms <= focusBudgetMs(preferred, limit: limit)) {
      return FocusChoice(preferred, FocusVariant.int8, limit, ms);
    }
  }
  final ms = cpuMs * _cpuFactor * limit;
  if (gpu) return FocusChoice(FocusModel.ezra, FocusVariant.fp16, limit, ms);
  if (mode == FocusMode.on || ms <= focusBudgetMs(FocusModel.ezra, limit: limit)) {
    return FocusChoice(FocusModel.ezra, FocusVariant.int8, limit, ms);
  }
  return FocusChoice.none;
}

/// Models that share Apollos's own longer budget (see kApollosBudgetMs) rather than
/// Ezra's -- a named, reusable set rather than an inline boolean, so a future model joining this tier does
/// not require touching every place that already checks it. Public: search_screen.dart's own timeout check
/// must use this too, not a second, easy-to-forget copy of "is this model Apollos-sized".
const apollosSizedModels = {FocusModel.apollos, FocusModel.priscilla, FocusModel.aquila};

/// Per-model allowance grows linearly with the requested number of results.
/// Runtime allows twice this budget for variation before cancelling scoring.
double focusBudgetMs(FocusModel model, {int limit = defaultFocusLimit}) =>
    (apollosSizedModels.contains(model) ? kApollosBudgetMs : kFocusBudgetMs) * limit / defaultFocusLimit;

/// Respect the selected count. Automatic may stop after three very slow searches;
/// On keeps trying. Neither mode silently changes the reader's result limit.
FocusChoice adapt(FocusChoice c, List<double> recentMs, FocusMode mode) {
  if (c.variant == FocusVariant.none || recentMs.length < 3) return c;
  final budget = focusBudgetMs(c.model, limit: c.k);
  final sorted = [...recentMs]..sort();
  final median = sorted[sorted.length ~/ 2];
  if (median >= 2 * budget && mode == FocusMode.automatic) return FocusChoice.none;
  return c;
}

/// [items] with the first `scores.length` reordered by score, highest first (ties keep their order); the rest unchanged.
List<T> focusOrder<T>(List<T> items, List<double> scores) {
  final n = scores.length.clamp(0, items.length);
  final idx = List.generate(n, (i) => i)..sort((a, b) => scores[b].compareTo(scores[a]) != 0 ? scores[b].compareTo(scores[a]) : a - b);
  return [for (final i in idx) items[i], ...items.skip(n)];
}

/// After a new trial: a model already installed stays (a busy machine or a new driver must not strand a downloaded
/// pack); the same model takes the new measurement; with nothing installed the trial decides.
FocusChoice keep(FocusChoice? old, FocusChoice fresh, {required FocusVariant installed}) {
  if (installed != FocusVariant.none && old?.variant == installed && fresh.variant != installed) return old!;
  return fresh;
}

/// Decides between the persisted fallback and a fresh trial without ever overriding an explicit user preference.
/// [preference] is the model resolved from the user's explicit choice or the app's current default; [fresh] is this
/// trial run's result; [before] is the previously persisted choice; [others] holds, for every non-Ezra model,
/// whether this
/// trial's own `choose()` call already found a usable tier for it (`installable`, i.e. `fresh.model == that model`)
/// and whether a pack for it is on this device (`installed`) -- a model with no entry in [others] is treated as
/// neither. An explicit Ezra preference is absolute. Otherwise the preferred non-Ezra model un-sticks a stale Ezra
/// fallback as soon as it's genuinely available, and -- mirroring `keep()` -- an installed non-Ezra pack wins
/// against routine re-trial noise (a chosen-but-not-downloaded one does not: the trial's fallback then decides).
FocusChoice resolveFallback({
  required FocusModel preference,
  required FocusChoice fresh,
  required FocusChoice? before,
  required Map<FocusModel, ({bool installable, bool installed})> others,
}) {
  if (preference == FocusModel.ezra) {
    if (before?.model == FocusModel.ezra && fresh.model != FocusModel.ezra) return before!;
    if (fresh.model == FocusModel.ezra) return fresh;
    return FocusChoice(FocusModel.ezra, fresh.variant, fresh.k, fresh.predictedMs); // never leak a non-Ezra model through
  }
  final state = others[preference];
  if (fresh.model == preference && (state?.installable ?? false)) return fresh; // genuinely available now: un-stick
  if ((state?.installed ?? false) && before?.model == preference && fresh.model != preference) return before!; // installed preference wins against noise
  return fresh; // still on the Ezra fallback; nothing to un-stick yet
}
