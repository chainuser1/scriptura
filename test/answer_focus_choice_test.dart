import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/services/engine/answer_focus.dart';

void main() {
  // The reference laptop: device trial 1839 ms, CPU int8 focus measured 1270 ms at 10 candidates.
  const laptop = 1839.0;

  group('choose', () {
    test('a working graphics chip gets the graphics model', () {
      final c = choose(cpuMs: laptop, gpu: true, mode: FocusMode.automatic);
      expect(c.variant, FocusVariant.fp16);
      expect(c.k, 10);
    });

    test('without graphics, a fast processor gets the CPU model with the most candidates within budget', () {
      final fast = choose(cpuMs: 600, gpu: false, mode: FocusMode.automatic); // 0.69 * 600 * 30 / 10 = 1242 ms
      expect(fast.variant, FocusVariant.int8);
      expect(fast.k, 30);
      final mid = choose(cpuMs: 1200, gpu: false, mode: FocusMode.automatic); // 15 -> 1242 ms, 30 -> 2484 ms
      expect(mid.k, 15);
      final here = choose(cpuMs: laptop, gpu: false, mode: FocusMode.automatic); // 10 -> 1269 ms
      expect((here.variant, here.k), (FocusVariant.int8, 10));
      expect(here.predictedMs, closeTo(1269, 1));
    });

    test('too slow for Automatic means none', () {
      expect(choose(cpuMs: 5000, gpu: false, mode: FocusMode.automatic).variant, FocusVariant.none);
    });

    test('Off is always none, even with graphics', () {
      expect(choose(cpuMs: 100, gpu: true, mode: FocusMode.off).variant, FocusVariant.none);
    });

    test('On still uses it when slow, with the fewest candidates', () {
      final c = choose(cpuMs: 5000, gpu: false, mode: FocusMode.on);
      expect((c.variant, c.k), (FocusVariant.int8, 10));
      expect(choose(cpuMs: 5000, gpu: true, mode: FocusMode.on).variant, FocusVariant.fp16);
    });
  });

  group('adapt (after install, from measured times)', () {
    const start = FocusChoice(FocusVariant.int8, 30, 1200);

    test('keeps the choice while searches are within budget', () {
      expect(adapt(start, [900, 1100, 1300], FocusMode.automatic), start);
    });

    test('steps down to fewer candidates when searches are slow', () {
      expect(adapt(start, [2600, 2500, 2700], FocusMode.automatic).k, 15);
      expect(adapt(const FocusChoice(FocusVariant.fp16, 15, 900), [2000, 2100, 1900], FocusMode.automatic).k, 10);
    });

    test('at 10 candidates and still far too slow, Automatic turns itself off; On keeps going', () {
      const ten = FocusChoice(FocusVariant.int8, 10, 1200);
      expect(adapt(ten, [3200, 3500, 3100], FocusMode.automatic).variant, FocusVariant.none);
      expect(adapt(ten, [3200, 3500, 3100], FocusMode.on), ten);
    });

    test('needs a few searches before judging', () {
      expect(adapt(start, [5000], FocusMode.automatic), start);
    });
  });

  test('choices survive being saved', () {
    const c = FocusChoice(FocusVariant.fp16, 15, 812.5);
    expect(FocusChoice.fromJson(c.toJson()), c);
    expect(FocusChoice.fromJson('nonsense'), isNull);
    expect(FocusMode.parse(null), FocusMode.automatic);
    expect(FocusMode.parse('off'), FocusMode.off);
  });
}
