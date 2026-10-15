import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/services/engine/engine_pack.dart';

void main() {
  test('the engine config turns volume balance on at the measured strength', () {
    final engine = InstalledPack(Directory('pack'), {
      'encoder_file': 'encoder.onnx',
      'profiles': <String, dynamic>{},
      'default_profile': 'compass',
      'fallback_without_thread': 'compass',
      'identity': <String, dynamic>{},
    });
    final cfg = EnginePaths(libraryPath: 'engine.dll', engine: engine).config();
    // tool/volume_balance.py STRENGTH, chosen by the Task 1 rule (docs/superpowers/plans/2026-10-14-volume-balance.md)
    expect(cfg['volume_balance'], 0.75);
  });
}
