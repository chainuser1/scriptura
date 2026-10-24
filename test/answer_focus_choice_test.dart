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

    test('preferring Apollos with a working graphics chip still goes through the int8/CPU ladder, not fp16/GPU (fp16 pack is broken for now)', () {
      // A fast-enough device: GPU being available no longer grants fp16 (removed until the pack is fixed), but a
      // working graphics chip says nothing about CPU speed, so this still has to go through Apollos's own CPU ladder.
      final c = choose(cpuMs: 600, gpu: true, mode: FocusMode.automatic, preferred: FocusModel.apollos);
      expect(c.model, FocusModel.apollos);
      expect(c.variant, FocusVariant.int8);
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

    test('preferring Apollos on a device too slow for its own 40s budget falls back to Ezra', () {
      // Apollos's budget is generous (40s -- the reader already opted into a slower, more refined search), so
      // this only happens on a genuinely very slow device: at cpuMs=4200, Apollos's own ladder exceeds 40000ms
      // even at k=10 (41748ms), and Ezra's 1500ms budget fails too at every k -- mode On keeps Ezra at k=10
      // anyway rather than giving up, which is what surfaces the fallback here.
      const verySlow = 4200.0;
      final apollos = choose(cpuMs: verySlow, gpu: false, mode: FocusMode.on, preferred: FocusModel.apollos);
      expect(apollos.model, FocusModel.ezra);
      expect(apollos.k, 10);
    });

    test('force overrides the budget fit check: Apollos is used even when it would not otherwise fit', () {
      // The reader explicitly chose to try Apollos anyway after being warned it may not fit their device.
      const verySlow = 4200.0;
      final c = choose(cpuMs: verySlow, gpu: false, mode: FocusMode.on, preferred: FocusModel.apollos, force: true);
      expect(c.model, FocusModel.apollos);
      expect(c.variant, FocusVariant.int8);
      expect(c.k, 10); // the smallest tier, since it's already known to be slow here
    });

    test('force has no effect when Apollos already fits on its own', () {
      const fast = 200.0;
      final forced = choose(cpuMs: fast, gpu: false, mode: FocusMode.automatic, preferred: FocusModel.apollos, force: true);
      final natural = choose(cpuMs: fast, gpu: false, mode: FocusMode.automatic, preferred: FocusModel.apollos);
      expect(forced, natural);
    });

    test('force is ignored when Ezra is the actual preference', () {
      final c = choose(cpuMs: laptop, gpu: false, mode: FocusMode.automatic, preferred: FocusModel.ezra, force: true);
      expect(c.model, FocusModel.ezra);
    });

    test('force does nothing when Answer focus is off', () {
      final c = choose(cpuMs: laptop, gpu: false, mode: FocusMode.off, preferred: FocusModel.apollos, force: true);
      expect(c.variant, FocusVariant.none);
    });

    test('force also overrides the budget fit check for Priscilla, mirroring Apollos', () {
      const extremelySlow = 100000.0;
      final c = choose(cpuMs: extremelySlow, gpu: false, mode: FocusMode.on, preferred: FocusModel.priscilla, force: true);
      expect(c.model, FocusModel.priscilla);
      expect(c.variant, FocusVariant.int8);
      expect(c.k, 10);
    });
  });

  group('choose (Priscilla)', () {
    test('Priscilla preferred and fitting returns the Priscilla int8 choice, using Apollos-sized headroom', () {
      final c = choose(cpuMs: 600.0, gpu: false, mode: FocusMode.automatic, preferred: FocusModel.priscilla);
      expect(c.model, FocusModel.priscilla);
      expect(c.variant, FocusVariant.int8);
    });

    test('Priscilla preferred but not fitting at any k under its own (Apollos-sized) budget falls back to Ezra', () {
      // _priscillaCpuFactor (0.069, Ezra's unmeasured placeholder) is far smaller than _apollosCpuFactor (0.994,
      // measured) -- the same 4200ms device speed that defeats Apollos's own ladder does NOT defeat Priscilla's
      // (4200*0.069*10 ~= 2898ms, well under kApollosBudgetMs). This needs a genuinely much slower device to
      // actually exceed kApollosBudgetMs even at Priscilla's own, much smaller, per-candidate cost.
      const extremelySlow = 100000.0; // 100000*0.069*10 ~= 69000ms > kApollosBudgetMs (40000ms) at every _apollosKs tier
      final c = choose(cpuMs: extremelySlow, gpu: false, mode: FocusMode.automatic, preferred: FocusModel.priscilla);
      expect(c.model, FocusModel.ezra);
    });

    test('Priscilla preferred but not fitting falls back to the smallest Ezra k under On, not none', () {
      const extremelySlow = 100000.0;
      final c = choose(cpuMs: extremelySlow, gpu: false, mode: FocusMode.on, preferred: FocusModel.priscilla);
      expect(c.model, FocusModel.ezra);
      expect(c.k, 10);
    });

    test('Priscilla preferred and fitting wins even on a device with a working graphics chip, mirroring Apollos', () {
      final c = choose(cpuMs: 600.0, gpu: true, mode: FocusMode.automatic, preferred: FocusModel.priscilla);
      expect(c.model, FocusModel.priscilla);
      expect(c.variant, FocusVariant.int8);
    });

    test('Priscilla and Apollos are evaluated independently against the shared budget/ladder, each with its own '
        'cost factor -- NOT a permanent guarantee that Priscilla always fits where Apollos doesn\'t: this is '
        'incidental to their current real factors (Priscilla ~0.134, Apollos 0.994, cross-calibrated 2026-10-25) '
        'and will need updating if either factor is re-measured and changes materially', () {
      const apollosDoesNotFitHere = 4200.0; // 4200*0.994*10 = 41748 > kApollosBudgetMs; 4200*0.134*10 = 5628, still fits
      final apollos = choose(cpuMs: apollosDoesNotFitHere, gpu: false, mode: FocusMode.automatic, preferred: FocusModel.apollos);
      final priscilla = choose(cpuMs: apollosDoesNotFitHere, gpu: false, mode: FocusMode.automatic, preferred: FocusModel.priscilla);
      expect(apollos.model, FocusModel.ezra, reason: 'Apollos genuinely does not fit at this speed');
      expect(priscilla.model, FocusModel.priscilla, reason: 'Priscilla, with its own real (much smaller) cost factor, still fits the same budget ceiling here');
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

  group('adapt (Priscilla)', () {
    test('Priscilla at k=10 (the floor) with a very slow median turns off under Automatic, same as Apollos would', () {
      const start = FocusChoice(FocusModel.priscilla, FocusVariant.int8, 10, 30000);
      final r = adapt(start, [85000.0, 86000.0, 84000.0], FocusMode.automatic); // >= 2x kApollosBudgetMs
      expect(r, FocusChoice.none);
    });

    test('Priscilla at k=10 under On mode never turns off, same as Apollos', () {
      const start = FocusChoice(FocusModel.priscilla, FocusVariant.int8, 10, 30000);
      final r = adapt(start, [85000.0, 86000.0, 84000.0], FocusMode.on);
      expect(r, start);
    });

    test('Priscilla steps down its own ladder the same shape as Apollos, not Ezra\'s', () {
      const start = FocusChoice(FocusModel.priscilla, FocusVariant.int8, 30, 2000);
      final r = adapt(start, [45000.0, 46000.0, 44000.0], FocusMode.automatic); // over kApollosBudgetMs, under 2x
      expect(r.k, 15); // _apollosKs[1], matching the same step-down shape Apollos's own ladder test uses
    });
  });

  group('choose (Aquila)', () {
    test('Aquila preferred and fitting returns the Aquila int8 choice, using Apollos-sized headroom', () {
      final c = choose(cpuMs: 200.0, gpu: false, mode: FocusMode.automatic, preferred: FocusModel.aquila);
      expect(c.model, FocusModel.aquila);
      expect(c.variant, FocusVariant.int8);
    });

    test('Aquila preferred but not fitting at any k under its own (Apollos-sized) budget falls back to Ezra', () {
      // _aquilaCpuFactor == _apollosCpuFactor (0.994), so Aquila's own fit boundary matches Apollos's real one:
      // the same 4200ms device speed that already defeats Apollos's ladder (4200*0.994*10 ~= 41748ms) defeats
      // Aquila's too -- unlike Priscilla's own much smaller placeholder factor, no inflated device speed is needed.
      const verySlow = 4200.0;
      final c = choose(cpuMs: verySlow, gpu: false, mode: FocusMode.automatic, preferred: FocusModel.aquila);
      expect(c.model, FocusModel.ezra);
    });

    test('Aquila preferred but not fitting falls back to the smallest Ezra k under On, not none', () {
      const verySlow = 4200.0;
      final c = choose(cpuMs: verySlow, gpu: false, mode: FocusMode.on, preferred: FocusModel.aquila);
      expect(c.model, FocusModel.ezra);
      expect(c.k, 10);
    });

    test('Aquila preferred and fitting wins even on a device with a working graphics chip, mirroring Apollos/Priscilla', () {
      final c = choose(cpuMs: 200.0, gpu: true, mode: FocusMode.automatic, preferred: FocusModel.aquila);
      expect(c.model, FocusModel.aquila);
      expect(c.variant, FocusVariant.int8);
    });

    test('force overrides the budget fit check for Aquila too, mirroring Apollos and Priscilla', () {
      const verySlow = 4200.0;
      final c = choose(cpuMs: verySlow, gpu: false, mode: FocusMode.on, preferred: FocusModel.aquila, force: true);
      expect(c.model, FocusModel.aquila);
      expect(c.variant, FocusVariant.int8);
      expect(c.k, 10);
    });
  });

  group('adapt (Aquila)', () {
    test('Aquila at k=10 (the floor) with a very slow median turns off under Automatic, same as Apollos/Priscilla would', () {
      const start = FocusChoice(FocusModel.aquila, FocusVariant.int8, 10, 30000);
      final r = adapt(start, [85000.0, 86000.0, 84000.0], FocusMode.automatic);
      expect(r, FocusChoice.none);
    });

    test('Aquila at k=10 under On mode never turns off, same as Apollos/Priscilla', () {
      const start = FocusChoice(FocusModel.aquila, FocusVariant.int8, 10, 30000);
      final r = adapt(start, [85000.0, 86000.0, 84000.0], FocusMode.on);
      expect(r, start);
    });

    test('Aquila steps down its own ladder the same shape as Apollos/Priscilla, not Ezra\'s', () {
      const start = FocusChoice(FocusModel.aquila, FocusVariant.int8, 30, 2000);
      final r = adapt(start, [45000.0, 46000.0, 44000.0], FocusMode.automatic);
      expect(r.k, 15);
    });
  });

  group('resolveFallback', () {
    const ezraChoice = FocusChoice(FocusModel.ezra, FocusVariant.int8, 10, 1200);
    const apollosChoice = FocusChoice(FocusModel.apollos, FocusVariant.fp16, 10, 800);
    const priscillaChoice = FocusChoice(FocusModel.priscilla, FocusVariant.int8, 10, 600);

    test('an explicit Ezra preference is never overridden to Apollos', () {
      final r = resolveFallback(preference: FocusModel.ezra, fresh: apollosChoice, before: ezraChoice,
          others: {FocusModel.apollos: (installable: true, installed: false)});
      expect(r.model, FocusModel.ezra);
    });

    test('an explicit Ezra preference is never overridden even on a first run with no persisted choice yet', () {
      final r = resolveFallback(preference: FocusModel.ezra, fresh: apollosChoice, before: null,
          others: {FocusModel.apollos: (installable: true, installed: false)});
      expect(r.model, FocusModel.ezra);
    });

    test('preferring Apollos, once genuinely installable, replaces a stale Ezra fallback', () {
      final r = resolveFallback(preference: FocusModel.apollos, fresh: apollosChoice, before: ezraChoice,
          others: {FocusModel.apollos: (installable: true, installed: false)});
      expect(r.model, FocusModel.apollos);
    });

    test('preferring Apollos but still not installable keeps the Ezra fallback (no regression)', () {
      final r = resolveFallback(preference: FocusModel.apollos, fresh: ezraChoice, before: ezraChoice,
          others: {FocusModel.apollos: (installable: false, installed: false)});
      expect(r.model, FocusModel.ezra);
    });

    test('a previous Apollos choice is kept against a noisy Ezra trial only when an Apollos pack is installed', () {
      final kept = resolveFallback(preference: FocusModel.apollos, fresh: ezraChoice, before: apollosChoice,
          others: {FocusModel.apollos: (installable: false, installed: true)});
      expect(kept, apollosChoice);
      final released = resolveFallback(preference: FocusModel.apollos, fresh: ezraChoice, before: apollosChoice,
          others: {FocusModel.apollos: (installable: false, installed: false)});
      expect(released, ezraChoice, reason: 'nothing downloaded to protect: the trial fallback decides');
    });

    test('preferring Priscilla, once genuinely installable, replaces a stale Ezra fallback', () {
      final r = resolveFallback(preference: FocusModel.priscilla, fresh: priscillaChoice, before: ezraChoice,
          others: {FocusModel.priscilla: (installable: true, installed: false)});
      expect(r.model, FocusModel.priscilla);
    });

    test('an explicit Ezra preference is never overridden to either Apollos or Priscilla when both are installed', () {
      final r = resolveFallback(preference: FocusModel.ezra, fresh: priscillaChoice, before: ezraChoice,
          others: {
            FocusModel.apollos: (installable: false, installed: true),
            FocusModel.priscilla: (installable: true, installed: true),
          });
      expect(r.model, FocusModel.ezra);
    });

    test('a previous Apollos choice is kept against a noisy trial even when Priscilla is also installed', () {
      final r = resolveFallback(preference: FocusModel.apollos, fresh: ezraChoice, before: apollosChoice,
          others: {
            FocusModel.apollos: (installable: false, installed: true),
            FocusModel.priscilla: (installable: true, installed: true),
          });
      expect(r, apollosChoice, reason: "Apollos's own installed state protects it; Priscilla's state must not interfere");
    });

    test('preferring Priscilla does not let Apollos\'s installed state protect a stale Apollos `before` '
        'when Priscilla itself is not installed (the two models\' installed state must not cross-contaminate)', () {
      const priscillaChoice = FocusChoice(FocusModel.priscilla, FocusVariant.int8, 10, 600);
      final r = resolveFallback(preference: FocusModel.priscilla, fresh: priscillaChoice, before: apollosChoice,
          others: {
            FocusModel.apollos: (installable: false, installed: true),
            FocusModel.priscilla: (installable: true, installed: false),
          });
      expect(r, priscillaChoice, reason: 'Apollos being installed must not protect it when the preference and fresh result are both Priscilla');
    });

    test('an explicit Ezra preference is never overridden to Apollos, Priscilla, or Aquila when all three are installed', () {
      const aquilaChoice = FocusChoice(FocusModel.aquila, FocusVariant.int8, 10, 600);
      final r = resolveFallback(preference: FocusModel.ezra, fresh: aquilaChoice, before: ezraChoice,
          others: {
            FocusModel.apollos: (installable: false, installed: true),
            FocusModel.priscilla: (installable: false, installed: true),
            FocusModel.aquila: (installable: true, installed: true),
          });
      expect(r.model, FocusModel.ezra);
    });

    test('a previous Aquila choice is kept against a noisy Ezra trial even when Apollos and Priscilla are also '
        'installed (proves the three-model others map does not let a sibling model\'s installed state leak in)', () {
      const aquilaChoice = FocusChoice(FocusModel.aquila, FocusVariant.int8, 10, 600);
      final r = resolveFallback(preference: FocusModel.aquila, fresh: ezraChoice, before: aquilaChoice,
          others: {
            FocusModel.apollos: (installable: false, installed: true),
            FocusModel.priscilla: (installable: false, installed: true),
            FocusModel.aquila: (installable: false, installed: true),
          });
      expect(r.model, FocusModel.aquila);
    });

    test('preferring Aquila does not let Apollos\'s or Priscilla\'s installed state protect a stale Aquila `before` '
        'when Aquila itself is not installed (the three models\' installed state must not cross-contaminate)', () {
      const aquilaChoice = FocusChoice(FocusModel.aquila, FocusVariant.int8, 10, 600);
      final r = resolveFallback(preference: FocusModel.aquila, fresh: ezraChoice, before: aquilaChoice,
          others: {
            FocusModel.apollos: (installable: false, installed: true),
            FocusModel.priscilla: (installable: false, installed: true),
            FocusModel.aquila: (installable: false, installed: false),
          });
      expect(r.model, FocusModel.ezra);
    });
  });

  group('focusBudgetMs', () {
    test('Apollos, Priscilla, and Aquila all share the long Apollos budget, not Ezra\'s short one', () {
      expect(focusBudgetMs(FocusModel.apollos), kApollosBudgetMs);
      expect(focusBudgetMs(FocusModel.priscilla), kApollosBudgetMs);
      expect(focusBudgetMs(FocusModel.aquila), kApollosBudgetMs);
      expect(focusBudgetMs(FocusModel.ezra), kFocusBudgetMs);
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

  test('a pre-existing persisted choice (saved before Priscilla existed) still decodes correctly', () {
    final old = '{"model":"ezra","variant":"int8","k":10,"predicted_ms":1200.0}';
    final c = FocusChoice.fromJson(old);
    expect(c!.model, FocusModel.ezra);
  });

  test('a device too slow for Priscilla still falls back under the new default, same as an explicit Priscilla pick would', () {
    // Using the real choose() function directly (not AppController), confirm: with preference == FocusModel.priscilla
    // (now the unset-pref default from app_controller.dart's focusModelPreference) and a device trial too slow at
    // every k under kApollosBudgetMs, choose() still falls back to Ezra exactly as it does for an explicit pick --
    // proves Task 1 introduced no special-casing of "default" vs "explicit" inside choose() itself.
    final choice = choose(cpuMs: 200000, gpu: false, preferred: FocusModel.priscilla, mode: FocusMode.automatic);
    expect(choice.model, FocusModel.ezra);
  });
}
