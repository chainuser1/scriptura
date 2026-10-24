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

    test('forceApollos overrides the budget fit check: Apollos is used even when it would not otherwise fit', () {
      // The reader explicitly chose to try Apollos anyway after being warned it may not fit their device.
      const verySlow = 4200.0;
      final c = choose(cpuMs: verySlow, gpu: false, mode: FocusMode.on, preferred: FocusModel.apollos, forceApollos: true);
      expect(c.model, FocusModel.apollos);
      expect(c.variant, FocusVariant.int8);
      expect(c.k, 10); // the smallest tier, since it's already known to be slow here
    });

    test('forceApollos has no effect when Apollos already fits on its own', () {
      const fast = 200.0;
      final forced = choose(cpuMs: fast, gpu: false, mode: FocusMode.automatic, preferred: FocusModel.apollos, forceApollos: true);
      final natural = choose(cpuMs: fast, gpu: false, mode: FocusMode.automatic, preferred: FocusModel.apollos);
      expect(forced, natural);
    });

    test('forceApollos is ignored when Ezra is the actual preference', () {
      final c = choose(cpuMs: laptop, gpu: false, mode: FocusMode.automatic, preferred: FocusModel.ezra, forceApollos: true);
      expect(c.model, FocusModel.ezra);
    });

    test('forceApollos does nothing when Answer focus is off', () {
      final c = choose(cpuMs: laptop, gpu: false, mode: FocusMode.off, preferred: FocusModel.apollos, forceApollos: true);
      expect(c.variant, FocusVariant.none);
    });
  });

  group('choose (Priscilla)', () {
    test('Priscilla preferred and fitting returns the Priscilla int8 choice', () {
      final c = choose(cpuMs: 50.0, gpu: false, mode: FocusMode.automatic, preferred: FocusModel.priscilla);
      expect(c.model, FocusModel.priscilla);
      expect(c.variant, FocusVariant.int8);
    });

    test('Priscilla preferred but not fitting at any k falls back the same way Ezra itself would under Automatic', () {
      final c = choose(cpuMs: 100000.0, gpu: false, mode: FocusMode.automatic, preferred: FocusModel.priscilla);
      expect(c, FocusChoice.none);
    });

    test('Priscilla preferred but not fitting falls back to the smallest Ezra k under On, not none', () {
      final c = choose(cpuMs: 100000.0, gpu: false, mode: FocusMode.on, preferred: FocusModel.priscilla);
      expect(c.model, FocusModel.ezra);
      expect(c.k, 10);
    });

    test('Priscilla preferred and fitting wins even on a device with a working graphics chip (Priscilla has no '
        'GPU tier of its own, but mirrors Apollos: an explicit non-Ezra preference beats the generic Ezra fp16/GPU '
        'default, the same way Apollos\'s own branch already does)', () {
      final c = choose(cpuMs: 50.0, gpu: true, mode: FocusMode.automatic, preferred: FocusModel.priscilla);
      expect(c.model, FocusModel.priscilla);
      expect(c.variant, FocusVariant.int8);
    });

    test('Priscilla preferred but not fitting falls back to Ezra fp16 when a graphics chip is available', () {
      final c = choose(cpuMs: 100000.0, gpu: true, mode: FocusMode.automatic, preferred: FocusModel.priscilla);
      expect(c.model, FocusModel.ezra);
      expect(c.variant, FocusVariant.fp16);
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
    test('Priscilla at k=10 (the floor) with a very slow median turns off under Automatic, same as Ezra would', () {
      const start = FocusChoice(FocusModel.priscilla, FocusVariant.int8, 10, 1000);
      final r = adapt(start, [4000.0, 4100.0, 3900.0], FocusMode.automatic);
      expect(r, FocusChoice.none);
    });

    test('Priscilla at k=10 under On mode never turns off, same as Ezra', () {
      const start = FocusChoice(FocusModel.priscilla, FocusVariant.int8, 10, 1000);
      final r = adapt(start, [4000.0, 4100.0, 3900.0], FocusMode.on);
      expect(r, start);
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
}
