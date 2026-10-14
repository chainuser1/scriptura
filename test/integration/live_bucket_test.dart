// First run against the REAL published bucket (kDefaultDataAddress): downloads about 4 GB, so it only runs when asked.
//
//   $env:SCRIPTURA_LIVE = '1'; flutter test test/integration/live_bucket_test.dart
@Timeout(Duration(minutes: 45))
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app_controller.dart';
import 'package:scriptures_reader_mobile/services/engine/search_models.dart';

void main() {
  final lib = File('engine/target/release/scripture_engine.dll');
  final run = Platform.environment['SCRIPTURA_LIVE'] == '1' && lib.existsSync();

  test('the published bucket installs by itself and answers questions', skip: run ? false : 'set SCRIPTURA_LIVE=1 to run (downloads ~4 GB)', () async {
    final root = Directory.systemTemp.createTempSync('scriptura-live-');
    addTearDown(() => root.deleteSync(recursive: true));
    final app = AppController(root: root, environment: {'SCRIPTURA_ENGINE_LIB': lib.absolute.path});
    await app.load();
    expect(app.missingData, {'release', 'engine', 'entities', 'answers', 'colbert'});

    final watch = Stopwatch()..start();
    await app.ensureData(includeOptional: true);
    expect(app.setupPhase, SetupPhase.idle, reason: app.setupError);
    expect(app.missingData, isEmpty);
    // ignore: avoid_print
    print('first run finished in ${watch.elapsed.inSeconds} s');

    expect(app.repository, isNotNull);
    expect(app.engineState, EngineState.ready, reason: app.engineProblem);
    expect(app.search.hasColbertPack, isTrue);
    expect(app.answers, isNotNull);

    final faith = await app.search.search(SearchRequest.search('What is faith?'));
    expect(faith.profile, 'compass');
    expect(faith.hits, hasLength(20));
    final ref = await app.search.search(SearchRequest.search('John 3:16'));
    expect(ref.reference!.firstVerseId, 26137);
    final place = await app.search.search(SearchRequest.search('Where is Bethlehem?'));
    expect(place.person!.people.first.entityId, startsWith('place:'));
    final who = await app.search.search(SearchRequest.search('Who is Captain Moroni?'));
    expect(who.person!.people.first.entityId, 'person:moroni_captain');
    final phrase = await app.search.search(SearchRequest.phrase('the Lord is my shepherd'));
    expect(phrase.total, greaterThanOrEqualTo(1));
    await app.close();
  });
}
