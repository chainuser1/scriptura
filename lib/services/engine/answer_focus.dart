import 'dart:convert';

/// Answer focus: which model this device uses (if any) and how many search results it reorders. Chosen from the
/// engine's device trial before anything is downloaded, then adjusted from the real times of the first searches.

/// The reader's setting (Settings › Advanced). Stored as pref `answer_focus`.
enum FocusMode {
  automatic,
  on,
  off;

  static FocusMode parse(String? s) => values.firstWhere((m) => m.name == s, orElse: () => FocusMode.automatic);
}

/// Which pack: `answer-focus-int8-v1` (CPU) or `answer-focus-fp16-v1` (graphics chip).
enum FocusVariant { none, int8, fp16 }

/// Which model: Ezra (always available), Apollos, or Priscilla. Ezra is also the "nothing chosen yet" placeholder.
enum FocusModel { ezra, apollos, priscilla }

/// A search should not wait longer than this for Answer focus (Ezra).
const kFocusBudgetMs = 1500.0;
const _ks = [30, 15, 10];

/// CPU Answer focus time per candidate relative to the device trial (measured on the reference laptop: trial 1839 ms,
/// 10 candidates 1270 ms).
const _cpuFactor = 0.069;

/// Apollos's own, much longer budget: measured real device data (see below) showed its int8/CPU tier
/// cannot fit Ezra's 1500ms "feels instant" budget at any reasonable candidate count, on any
/// realistic device speed -- not a tuning problem, a real size difference (Apollos is a ~1.24B-param
/// Llama-family cross-encoder; Ezra's bge-reranker-v2-m3 is much smaller). Apollos's own copy already
/// tells the reader "on some devices it takes a bit longer" -- this budget is what makes that honest.
/// Owner's choice (2026-10-19, raised from 15s to 40s same day): room for k=10 even on somewhat slower
/// devices than the one this constant was calibrated on. A search that finishes sooner returns right
/// away -- this is a ceiling before Automatic gives up and falls back, never a fixed wait.
const kApollosBudgetMs = 40000.0;

/// Apollos's own CPU-tier candidate-count ladder, independent of Ezra's `_ks`.
const _apollosKs = [30, 15, 10];

/// Apollos's own CPU cost-per-candidate constant, measured on a real Android phone (2026-10-19):
/// device trial cpu_ms 1238/1295 (avg 1267), k=10 completed in 12846/12342 ms (avg 12594) -- a real,
/// unforced `session.run()` time, not a timeout. `12594 / (1267 * 10)` ~= 0.994. This replaces an
/// earlier UNMEASURED placeholder (`_cpuFactor * 2`) that assumed Apollos cost about the same per
/// candidate as Ezra's much smaller model -- it does not: this is ~14x Ezra's `_cpuFactor`.
/// `adapt()`'s step-down logic still corrects this further from real search times, same as for Ezra.
const _apollosCpuFactor = 0.994;

/// UNMEASURED placeholder: reuses Ezra's `_cpuFactor` (0.069), calibrated for Ezra's model size, not
/// Priscilla's. Real per-candidate cost for Priscilla has not been measured against a phone-class device
/// trial yet -- only a desktop's raw ms/candidate (see docs/superpowers/specs/2026-10-24-priscilla-app-wiring-design.md).
/// Replace once real device data comes in, same as `_apollosCpuFactor` itself once was.
const _priscillaCpuFactor = _cpuFactor;

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
      return FocusChoice(model, FocusVariant.values.byName(m['variant'] as String), m['k'] as int, (m['predicted_ms'] as num).toDouble());
    } catch (_) {
      return null;
    }
  }

  @override
  bool operator ==(Object other) =>
      other is FocusChoice && other.model == model && other.variant == variant && other.k == k && other.predictedMs == predictedMs;
  @override
  int get hashCode => Object.hash(model, variant, k, predictedMs);
  @override
  String toString() => 'FocusChoice(${model.name}, ${variant.name}, $k, ${predictedMs.round()} ms)';
}

/// The choice from the device trial: a working graphics chip gets the graphics model; otherwise the CPU model with the
/// most candidates that fit the budget. Automatic declines a device too slow for even 10; On uses 10 anyway. Apollos is
/// used when preferred and it fits; otherwise (no Apollos candidate fits) the Ezra logic decides. Apollos's fp16/GPU
/// tier is temporarily unavailable (a real pack defect, not a device limitation) -- Apollos only ever offers int8/CPU
/// for now, even on a GPU-capable device, until that pack is fixed.
///
/// [force]: the reader was warned [preferred] likely won't fit this device and chose to try it anyway. Skips the
/// budget-fit check entirely and uses that model's smallest tier (already known to be slow here) -- never applies
/// when [preferred] is Ezra, and never brings Answer focus back from Off.
FocusChoice choose({
  required double cpuMs,
  required bool gpu,
  required FocusMode mode,
  required FocusModel preferred,
  bool force = false,
}) {
  if (mode == FocusMode.off) return FocusChoice.none;
  final cpu10 = cpuMs * _cpuFactor * 10;
  if (preferred == FocusModel.apollos) {
    // Apollos's fp16/GPU pack has a real ONNX export defect (DirectML rejects it; see memory
    // apollos-fp16-gpu-broken-int8-only-for-now) -- not yet fixed/re-uploaded. Until it is, a
    // GPU-capable device still gets Apollos, just on its working int8/CPU tier below, not fp16/GPU.
    // Apollos's own budget is much longer than Ezra's -- see kApollosBudgetMs.
    for (final k in _apollosKs) {
      final ms = cpuMs * _apollosCpuFactor * k;
      if (ms <= kApollosBudgetMs) return FocusChoice(FocusModel.apollos, FocusVariant.int8, k, ms);
    }
    if (force) return FocusChoice(FocusModel.apollos, FocusVariant.int8, 10, cpuMs * _apollosCpuFactor * 10);
  }
  if (preferred == FocusModel.priscilla) {
    // Priscilla has no GPU/fp16 tier of its own (not a temporary pack defect like Apollos's -- see Global
    // Constraints), but mirrors Apollos's own branch above: an explicit non-Ezra preference beats the generic
    // Ezra fp16/GPU default below when it fits, rather than a GPU device silently ignoring the reader's pick.
    // Priscilla reuses Apollos's own budget and candidate ladder (kApollosBudgetMs, _apollosKs), not Ezra's: a
    // tight Ezra-shaped budget was rationing Priscilla to too few candidates for its real size, hurting search
    // quality -- Apollos's generous headroom is the better (if still unmeasured) guess for a model Priscilla's
    // weight class, same reasoning kApollosBudgetMs's own comment already gives for Apollos itself.
    for (final k in _apollosKs) {
      final ms = cpuMs * _priscillaCpuFactor * k;
      if (ms <= kApollosBudgetMs) return FocusChoice(FocusModel.priscilla, FocusVariant.int8, k, ms);
    }
    if (force) return FocusChoice(FocusModel.priscilla, FocusVariant.int8, 10, cpuMs * _priscillaCpuFactor * 10);
  }
  if (gpu) return FocusChoice(FocusModel.ezra, FocusVariant.fp16, 10, cpu10); // first searches measure the real graphics time
  for (final k in _ks) {
    final ms = cpuMs * _cpuFactor * k;
    if (ms <= kFocusBudgetMs) return FocusChoice(FocusModel.ezra, FocusVariant.int8, k, ms);
  }
  return mode == FocusMode.on ? FocusChoice(FocusModel.ezra, FocusVariant.int8, 10, cpu10) : FocusChoice.none;
}

/// After install: with at least three measured searches, fewer candidates when the median is over budget; at 10 and
/// still over twice the budget, Automatic turns Answer focus off (On keeps it). Apollos and Priscilla both use the
/// longer budget and ladder (see kApollosBudgetMs) -- Ezra's own are not big enough for either model's real size.
FocusChoice adapt(FocusChoice c, List<double> recentMs, FocusMode mode) {
  if (c.variant == FocusVariant.none || recentMs.length < 3) return c;
  final apollosSized = c.model == FocusModel.apollos || c.model == FocusModel.priscilla;
  final budget = apollosSized ? kApollosBudgetMs : kFocusBudgetMs;
  final ks = apollosSized ? _apollosKs : _ks;
  final sorted = [...recentMs]..sort();
  final median = sorted[sorted.length ~/ 2];
  if (median <= budget) return c;
  final i = ks.indexOf(c.k);
  if (i >= 0 && i < ks.length - 1) return FocusChoice(c.model, c.variant, ks[i + 1], median * ks[i + 1] / c.k);
  if (median >= 2 * budget && mode == FocusMode.automatic) return FocusChoice.none; // a timeout counts
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
/// [preference] is what the user actually wants (an explicit choice; Ezra by default); [fresh] is this trial run's
/// result; [before] is the previously persisted choice; [others] holds, for every non-Ezra model, whether this
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
