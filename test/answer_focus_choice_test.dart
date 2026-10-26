import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/services/engine/answer_focus.dart';

void main() {
  for (final model in FocusModel.values) {
    // Trial cost per candidate, calibrated independently for each model.
    final factor = switch (model) {
      FocusModel.ezra => 0.069,
      FocusModel.priscilla => 0.134,
      _ => 0.994,
    };
    final budget = focusBudgetMs(model);
    group(model.name, () {
      for (final (capacity, expected) in [(110, 100), (90, 80), (70, 60)]) {
        test('chooses $expected candidates when $capacity fit', () {
          final c = choose(cpuMs: budget / (factor * capacity), gpu: false,
              mode: FocusMode.automatic, preferred: model);
          expect(c.model, model);
          expect(c.variant, FocusVariant.int8);
          expect(c.k, expected);
          expect(c.predictedMs, closeTo(budget * expected / capacity, 0.01));
        });
      }
      test('Off stays off, including forced choices and graphics', () {
        expect(choose(cpuMs: 100, gpu: true, mode: FocusMode.off,
            preferred: model, force: true), FocusChoice.none);
      });
      test('very slow Automatic devices retain the existing fallback policy', () {
        expect(choose(cpuMs: 200000, gpu: false, mode: FocusMode.automatic,
            preferred: model), FocusChoice.none);
      });
      test('On keeps a minimum of 60 even on a slow device', () {
        final c = choose(cpuMs: 200000, gpu: false, mode: FocusMode.on,
            preferred: model, force: true);
        expect(c.model, model);
        expect(c.k, 60);
        expect(c.variant, FocusVariant.int8);
      });
      test('a fitting preferred model wins on a GPU-capable device', () {
        final c = choose(cpuMs: 100, gpu: true, mode: FocusMode.automatic,
            preferred: model);
        expect(c.model, model);
        expect(c.variant, model == FocusModel.ezra ? FocusVariant.fp16 : FocusVariant.int8);
        expect(c.k, model == FocusModel.ezra ? 60 : 100);
      });
      test('force has no effect on an already fitting model', () {
        expect(choose(cpuMs: 100, gpu: false, mode: FocusMode.on, preferred: model, force: true),
            choose(cpuMs: 100, gpu: false, mode: FocusMode.on, preferred: model));
      });
      test('adaptation steps 100 to 80 to 60 and never below 60', () {
        final start = FocusChoice(model, FocusVariant.int8, 100, budget);
        final slow = [budget * 1.2, budget * 1.3, budget * 1.4];
        expect(adapt(start, [budget], FocusMode.automatic), start);
        expect(adapt(start, [budget / 2, budget, budget], FocusMode.automatic), start);
        final middle = adapt(start, slow, FocusMode.automatic);
        expect(middle.k, 80);
        final floor = adapt(middle, slow, FocusMode.automatic);
        expect(floor.k, 60);
        expect(adapt(floor, slow, FocusMode.automatic), floor);
        final timeout = List<double>.filled(3, 2 * budget);
        expect(adapt(floor, timeout, FocusMode.automatic), FocusChoice.none);
        expect(adapt(floor, timeout, FocusMode.on), floor);
      });
      test('saved legacy choices upgrade without losing model or cost estimate', () {
        for (final k in [10, 15, 30]) {
          final c = FocusChoice.fromJson(FocusChoice(model, FocusVariant.int8, k, k * 100).toJson())!;
          expect(c.model, model);
          expect(c.variant, FocusVariant.int8);
          expect(c.k, 60);
          expect(c.predictedMs, 6000);
        }
        for (final k in [60, 80, 100]) {
          final c = FocusChoice(model, FocusVariant.int8, k, k * 100);
          expect(FocusChoice.fromJson(c.toJson()), c);
        }
      });
    });
  }

  test('GPU choice starts at 60 until real searches measure graphics time', () {
    final c = choose(cpuMs: 1839, gpu: true, mode: FocusMode.automatic, preferred: FocusModel.ezra);
    expect(c.k, 60);
    expect(c.predictedMs, closeTo(7613.46, 0.01));
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
    const c = FocusChoice(FocusModel.apollos, FocusVariant.fp16, 80, 812.5);
    expect(FocusChoice.fromJson(c.toJson()), c);
    expect(FocusChoice.fromJson('nonsense'), isNull);
    // Saved before the model field existed: still loads, as Ezra.
    expect(FocusChoice.fromJson('{"variant":"int8","k":10,"predicted_ms":1269.0}')?.model, FocusModel.ezra);
    expect(FocusMode.parse(null), FocusMode.automatic);
    expect(FocusMode.parse('off'), FocusMode.off);
  });

  test('a pre-existing persisted choice (saved before Priscilla existed) still decodes correctly', () {
    const old = '{"model":"ezra","variant":"int8","k":10,"predicted_ms":1200.0}';
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
