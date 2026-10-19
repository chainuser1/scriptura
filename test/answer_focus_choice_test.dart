import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/services/engine/answer_focus.dart';

void main() {
  // The reference laptop: device trial 1839 ms, CPU int8 focus measured 1270 ms at 10 candidates.
  const laptop = 1839.0;

  group('choose', () {
    test('a working graphics chip gets the graphics model', () {
      final c = choose(cpuMs: laptop, gpu: true, mode: FocusMode.automatic, preferred: FocusModel.ezra);
      expect(c.variant, FocusVariant.fp16);
      expect(c.k, 10);
    });

    test('without graphics, a fast processor gets the CPU model with the most candidates within budget', () {
      final fast = choose(cpuMs: 600, gpu: false, mode: FocusMode.automatic, preferred: FocusModel.ezra); // 0.69 * 600 * 30 / 10 = 1242 ms
      expect(fast.variant, FocusVariant.int8);
      expect(fast.k, 30);
      final mid = choose(cpuMs: 1200, gpu: false, mode: FocusMode.automatic, preferred: FocusModel.ezra); // 15 -> 1242 ms, 30 -> 2484 ms
      expect(mid.k, 15);
      final here = choose(cpuMs: laptop, gpu: false, mode: FocusMode.automatic, preferred: FocusModel.ezra); // 10 -> 1269 ms
      expect((here.variant, here.k), (FocusVariant.int8, 10));
      expect(here.predictedMs, closeTo(1269, 1));
    });

    test('too slow for Automatic means none', () {
      expect(choose(cpuMs: 5000, gpu: false, mode: FocusMode.automatic, preferred: FocusModel.ezra).variant, FocusVariant.none);
    });

    test('Off is always none, even with graphics', () {
      expect(choose(cpuMs: 100, gpu: true, mode: FocusMode.off, preferred: FocusModel.ezra).variant, FocusVariant.none);
    });

    test('On still uses it when slow, with the fewest candidates', () {
      final c = choose(cpuMs: 5000, gpu: false, mode: FocusMode.on, preferred: FocusModel.ezra);
      expect((c.variant, c.k), (FocusVariant.int8, 10));
      expect(choose(cpuMs: 5000, gpu: true, mode: FocusMode.on, preferred: FocusModel.ezra).variant, FocusVariant.fp16);
    });

    test('preferring Apollos with a working graphics chip gets Apollos fp16', () {
      final c = choose(cpuMs: laptop, gpu: true, mode: FocusMode.automatic, preferred: FocusModel.apollos);
      expect(c.model, FocusModel.apollos);
      expect(c.variant, FocusVariant.fp16);
    });

    test('preferring Apollos without a graphics chip gets Apollos int8 on a fast-enough device', () {
      final c = choose(cpuMs: 600, gpu: false, mode: FocusMode.automatic, preferred: FocusModel.apollos);
      expect(c.model, FocusModel.apollos);
      expect(c.variant, FocusVariant.int8);
    });

    test('preferring Apollos on a device too slow for even its smallest int8 candidate count falls back to Ezra', () {
      final c = choose(cpuMs: 50000, gpu: false, mode: FocusMode.automatic, preferred: FocusModel.apollos);
      expect(c.model, FocusModel.ezra); // Apollos's own ladder (Task 5) found nothing that fits; fall back
    });

    test('preferring Ezra always gets Ezra, with or without graphics', () {
      expect(choose(cpuMs: laptop, gpu: true, mode: FocusMode.automatic, preferred: FocusModel.ezra).model, FocusModel.ezra);
      expect(choose(cpuMs: laptop, gpu: false, mode: FocusMode.automatic, preferred: FocusModel.ezra).model, FocusModel.ezra);
    });

    test('Apollos gpu choice starts at k=10, independent of the CPU budget constant', () {
      final apollos = choose(cpuMs: laptop, gpu: true, mode: FocusMode.automatic, preferred: FocusModel.apollos);
      final ezra = choose(cpuMs: laptop, gpu: true, mode: FocusMode.automatic, preferred: FocusModel.ezra);
      expect(apollos.k, ezra.k); // both 10 today, by coincidence of the shared starting point, not a shared constant
      expect(apollos.model, FocusModel.apollos);
      expect(ezra.model, FocusModel.ezra);
    });

    test('Apollos CPU ladder predicts cost from its own constant, not Ezra\'s', () {
      const fast = 200.0; // fast enough both ladders fit at k=30 with room to spare (414ms / 828ms vs 1500 budget)
      final apollos = choose(cpuMs: fast, gpu: false, mode: FocusMode.automatic, preferred: FocusModel.apollos);
      final ezra = choose(cpuMs: fast, gpu: false, mode: FocusMode.automatic, preferred: FocusModel.ezra);
      expect(apollos.model, FocusModel.apollos); // confirms it didn't fall back to Ezra at this speed
      expect(apollos.k, 30);
      expect(ezra.k, 30);
      // Same device, same k -- but the predicted ms must come from Apollos's own constant, not Ezra's:
      expect(apollos.predictedMs, isNot(equals(ezra.predictedMs)));
    });

    test('preferring Apollos on a device too slow for its own ladder at the reference laptop speed falls back to Ezra', () {
      // At laptop=1839ms, Apollos's _apollosCpuFactor (2x Ezra's) makes even k=10 exceed the 1500ms budget (2537.8ms),
      // while Ezra's own ladder still fits at k=10 (1268.9ms) -- this is a real, correct divergence between the two
      // ladders at this device speed, not a test artifact.
      final apollos = choose(cpuMs: laptop, gpu: false, mode: FocusMode.automatic, preferred: FocusModel.apollos);
      expect(apollos.model, FocusModel.ezra);
      expect(apollos.k, 10);
    });
  });

  group('adapt (after install, from measured times)', () {
    const start = FocusChoice(FocusModel.ezra, FocusVariant.int8, 30, 1200);

    test('keeps the choice while searches are within budget', () {
      expect(adapt(start, [900, 1100, 1300], FocusMode.automatic), start);
    });

    test('steps down to fewer candidates when searches are slow', () {
      expect(adapt(start, [2600, 2500, 2700], FocusMode.automatic).k, 15);
      expect(adapt(const FocusChoice(FocusModel.ezra, FocusVariant.fp16, 15, 900), [2000, 2100, 1900], FocusMode.automatic).k, 10);
    });

    test('at 10 candidates and still far too slow, Automatic turns itself off; On keeps going', () {
      const ten = FocusChoice(FocusModel.ezra, FocusVariant.int8, 10, 1200);
      expect(adapt(ten, [3200, 3500, 3100], FocusMode.automatic).variant, FocusVariant.none);
      expect(adapt(ten, [3200, 3500, 3100], FocusMode.on), ten);
    });

    test('needs a few searches before judging', () {
      expect(adapt(start, [5000], FocusMode.automatic), start);
    });
  });

  group('resolveFallback', () {
    const ezraChoice = FocusChoice(FocusModel.ezra, FocusVariant.int8, 10, 1200);
    const apollosChoice = FocusChoice(FocusModel.apollos, FocusVariant.fp16, 10, 800);

    test('an explicit Ezra preference is never overridden to Apollos', () {
      final r = resolveFallback(preference: FocusModel.ezra, fresh: apollosChoice, before: ezraChoice, apollosInstallable: true);
      expect(r.model, FocusModel.ezra);
    });

    test('an explicit Ezra preference is never overridden even on a first run with no persisted choice yet', () {
      final r = resolveFallback(preference: FocusModel.ezra, fresh: apollosChoice, before: null, apollosInstallable: true);
      expect(r.model, FocusModel.ezra);
    });

    test('preferring Apollos, once genuinely installable, replaces a stale Ezra fallback', () {
      final r = resolveFallback(preference: FocusModel.apollos, fresh: apollosChoice, before: ezraChoice, apollosInstallable: true);
      expect(r.model, FocusModel.apollos);
    });

    test('preferring Apollos but still not installable keeps the Ezra fallback (no regression)', () {
      final r = resolveFallback(preference: FocusModel.apollos, fresh: ezraChoice, before: ezraChoice, apollosInstallable: false);
      expect(r.model, FocusModel.ezra);
    });
  });

  test('choices survive being saved', () {
    const c = FocusChoice(FocusModel.apollos, FocusVariant.fp16, 15, 812.5);
    expect(FocusChoice.fromJson(c.toJson()), c);
    expect(FocusChoice.fromJson('nonsense'), isNull);
    // Saved before the model field existed: still loads, as Ezra.
    expect(FocusChoice.fromJson('{"variant":"int8","k":10,"predicted_ms":1269.0}')?.model, FocusModel.ezra);
    expect(FocusMode.parse(null), FocusMode.automatic);
    expect(FocusMode.parse('off'), FocusMode.off);
  });
}
