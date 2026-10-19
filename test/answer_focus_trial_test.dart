import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app_controller.dart';
import 'package:scriptures_reader_mobile/data/user/user_store.dart';
import 'package:scriptures_reader_mobile/services/engine/answer_focus.dart';
import 'package:scriptures_reader_mobile/services/engine/search_models.dart';

import 'fakes/fake_search_service.dart';

void main() {
  (AppController, FakeSearchService) setup({bool gpu = true}) {
    final svc = FakeSearchService((r, id) async => SearchResponse(mode: 'device_trial', raw: {'cpu_ms': 1839.0, 'gpu': gpu && r.body?['probe_gpu'] != false}));
    return (AppController.fixed(search: svc, user: UserStore.memory()), svc);
  }

  test('a trial that never finished (a crashing graphics driver) skips the graphics probe next time', () async {
    final (app, svc) = setup();
    app.user.setPref('focus_trial_pending', '1');
    await app.measureDevice();
    expect(svc.requests.single.body!['probe_gpu'], false);
    expect(app.focusChoice!.variant, FocusVariant.int8);
    expect(app.user.pref('focus_trial_pending'), isNot('1'), reason: 'finished');
  });

  test('a normal trial probes the graphics chip and is marked pending while it runs', () async {
    final (app, svc) = setup();
    await app.measureDevice();
    expect(svc.requests.single.body!['probe_gpu'], isNot(false));
    expect(app.focusChoice!.variant, FocusVariant.fp16);
  });

  group('keep', () {
    const int8 = FocusChoice(FocusModel.ezra, FocusVariant.int8, 10, 1200);
    const fp16 = FocusChoice(FocusModel.ezra, FocusVariant.fp16, 10, 1200);

    test('an installed model is kept when a new trial would pick the other one', () {
      expect(keep(int8, fp16, installed: FocusVariant.int8), int8);
      expect(keep(int8, FocusChoice.none, installed: FocusVariant.int8), int8, reason: 'a busy machine does not orphan the pack');
    });

    test('with nothing installed the new trial decides', () {
      expect(keep(int8, fp16, installed: FocusVariant.none), fp16);
      expect(keep(null, int8, installed: FocusVariant.none), int8);
    });

    test('the same model takes the new measurement', () {
      const faster = FocusChoice(FocusModel.ezra, FocusVariant.int8, 30, 900);
      expect(keep(int8, faster, installed: FocusVariant.int8), faster);
    });
  });
}
