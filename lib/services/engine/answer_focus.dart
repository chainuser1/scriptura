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

/// Which model: Ezra (always available) or Apollos. Ezra is also the "nothing chosen yet" placeholder.
enum FocusModel { ezra, apollos }

/// A search should not wait longer than this for Answer focus.
const kFocusBudgetMs = 1500.0;
const _ks = [30, 15, 10];

/// CPU Answer focus time per candidate relative to the device trial (measured on the reference laptop: trial 1839 ms,
/// 10 candidates 1270 ms).
const _cpuFactor = 0.069;

/// Apollos's own starting GPU candidate count, independent of Ezra's: mirrors Ezra's fp16 starting k=10 as a
/// conservative guess; `adapt()` corrects it from real measured search times.
const _apollosGpuK = 10;

/// Apollos's own CPU-tier candidate-count ladder, independent of Ezra's `_ks`.
const _apollosKs = [30, 15, 10];

/// Apollos's own CPU cost-per-candidate constant. UNMEASURED: no device has benchmarked Apollos's ~1.24B-parameter
/// Llama-family int8 (weight-only, computes in fp32) pack yet, so this is not Ezra's `_cpuFactor` -- that would
/// silently assume Apollos costs the same per candidate as Ezra's bge-reranker-v2-m3. Placeholder: at least double
/// Ezra's cost until a real-device pass replaces it; `adapt()`'s step-down logic corrects it from real search times
/// exactly as it already does for Ezra.
const _apollosCpuFactor = _cpuFactor * 2;

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
/// used when preferred and it fits; otherwise (no Apollos candidate fits) the Ezra logic decides.
FocusChoice choose({required double cpuMs, required bool gpu, required FocusMode mode, required FocusModel preferred}) {
  if (mode == FocusMode.off) return FocusChoice.none;
  final cpu10 = cpuMs * _cpuFactor * 10;
  if (preferred == FocusModel.apollos) {
    if (gpu) return FocusChoice(FocusModel.apollos, FocusVariant.fp16, _apollosGpuK, cpuMs * _cpuFactor * _apollosGpuK);
    for (final k in _apollosKs) {
      final ms = cpuMs * _apollosCpuFactor * k;
      if (ms <= kFocusBudgetMs) return FocusChoice(FocusModel.apollos, FocusVariant.int8, k, ms);
    }
  }
  if (gpu) return FocusChoice(FocusModel.ezra, FocusVariant.fp16, 10, cpu10); // first searches measure the real graphics time
  for (final k in _ks) {
    final ms = cpuMs * _cpuFactor * k;
    if (ms <= kFocusBudgetMs) return FocusChoice(FocusModel.ezra, FocusVariant.int8, k, ms);
  }
  return mode == FocusMode.on ? FocusChoice(FocusModel.ezra, FocusVariant.int8, 10, cpu10) : FocusChoice.none;
}

/// After install: with at least three measured searches, fewer candidates when the median is over budget; at 10 and
/// still over twice the budget, Automatic turns Answer focus off (On keeps it).
FocusChoice adapt(FocusChoice c, List<double> recentMs, FocusMode mode) {
  if (c.variant == FocusVariant.none || recentMs.length < 3) return c;
  final sorted = [...recentMs]..sort();
  final median = sorted[sorted.length ~/ 2];
  if (median <= kFocusBudgetMs) return c;
  final i = _ks.indexOf(c.k);
  if (i >= 0 && i < _ks.length - 1) return FocusChoice(c.model, c.variant, _ks[i + 1], median * _ks[i + 1] / c.k);
  if (median >= 2 * kFocusBudgetMs && mode == FocusMode.automatic) return FocusChoice.none; // a timeout counts
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
/// [preference] is what the user actually wants (explicit choice, or Apollos by default); [fresh] is this trial run's
/// result; [before] is the previously persisted choice; [apollosInstallable] is true when this trial's own `choose()`
/// call already found a usable Apollos tier (i.e. `fresh.model == FocusModel.apollos`). An explicit Ezra preference is
/// absolute. Otherwise Apollos un-sticks a stale Ezra fallback as soon as it's genuinely available, and -- mirroring
/// `keep()` -- whichever model is already installed wins against routine re-trial noise.
FocusChoice resolveFallback({
  required FocusModel preference,
  required FocusChoice fresh,
  required FocusChoice? before,
  required bool apollosInstallable,
}) {
  if (preference == FocusModel.ezra) {
    if (before?.model == FocusModel.ezra && fresh.model != FocusModel.ezra) return before!;
    if (fresh.model == FocusModel.ezra) return fresh;
    return FocusChoice(FocusModel.ezra, fresh.variant, fresh.k, fresh.predictedMs); // never leak Apollos through
  }
  if (fresh.model == FocusModel.apollos && apollosInstallable) return fresh; // genuinely available now: un-stick
  if (before?.model == FocusModel.apollos && fresh.model != FocusModel.apollos) return before!; // installed Apollos wins against noise
  return fresh; // still on the Ezra fallback; nothing to un-stick yet
}
