// The real hosting folders served over HTTP (with Range) by a local server, downloaded, verified and installed by the
// real AppController, then searched. Proves the published layout and the app agree. Skipped when not staged.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/app_controller.dart';
import 'package:scriptures_reader_mobile/services/engine/search_models.dart';

/// Serves files by name from several folders (the bucket root is the union of what is uploaded), with Range support.
Future<HttpServer> serve(List<Directory> roots) async {
  final server = await HttpServer.bind('127.0.0.1', 0);
  server.listen((req) async {
    final name = req.uri.pathSegments.join('/');
    final file = roots.map((r) => File('${r.path}/$name')).where((f) => f.existsSync()).firstOrNull;
    if (file == null) {
      req.response.statusCode = 404;
      await req.response.close();
      return;
    }
    final len = file.lengthSync();
    var start = 0;
    final range = req.headers.value(HttpHeaders.rangeHeader);
    if (range != null) {
      start = int.parse(range.substring(6).split('-').first);
      req.response.statusCode = 206;
    }
    req.response.contentLength = len - start;
    await req.response.addStream(file.openRead(start));
    await req.response.close();
  });
  return server;
}

void main() {
  final hosting = Directory('../scriptura/artifacts/hosting');
  final lib = File('engine/target/release/scripture_engine.dll');
  final ready = File('${hosting.path}/bucket/index.json').existsSync() && lib.existsSync();

  test('first run: the app fetches everything from the bucket layout by itself', skip: ready ? false : 'hosting not staged', () async {
    // the bucket root = bucket/ (index.json, content zip) + the two pack zips that sit in search-data/
    final server = await serve([Directory('${hosting.path}/bucket'), Directory('${hosting.path}/search-data')]);
    addTearDown(() => server.close(force: true));
    final root = Directory.systemTemp.createTempSync('scriptura-dl-');
    addTearDown(() => root.deleteSync(recursive: true));
    final app = AppController(root: root, environment: {'SCRIPTURA_ENGINE_LIB': lib.absolute.path});
    await app.load();
    expect(app.repository, isNull);
    expect(app.missingData, {'release', 'engine', 'entities', 'answers', 'colbert'});

    var sawUnpacking = false;
    app.addListener(() => sawUnpacking |= app.setupPhase == SetupPhase.unpacking);
    final address = 'http://127.0.0.1:${server.port}/';
    await app.ensureData(address: address);
    expect(app.setupPhase, SetupPhase.idle, reason: app.setupError);
    expect(sawUnpacking, isTrue);
    expect(app.missingData, {'colbert'}, reason: 'the optional 3 GB index is never fetched unasked');
    expect(app.answers, isNotNull, reason: 'the study-questions pack installed and opened');
    expect(app.engineState, EngineState.ready);
    expect(app.search.hasColbertPack, isFalse);
    await app.ensureData(address: address, includeOptional: true);
    expect(app.setupPhase, SetupPhase.idle, reason: app.setupError);
    expect(app.missingData, isEmpty);
    expect(app.repository, isNotNull);
    expect(app.engineState, EngineState.ready, reason: app.engineProblem);
    expect(app.search.hasColbertPack, isTrue);
    expect(Directory('${root.path}/scriptura/downloads').listSync().whereType<File>(), isEmpty, reason: 'archives are removed');

    final place = await app.search.search(SearchRequest.search('Where is Bethlehem?'));
    expect(place.person!.people.first.entityId, startsWith('place:'), reason: 'the entities pack knows places');
    final r = await app.search.search(SearchRequest.search('John 3:16'));
    expect(r.reference!.firstVerseId, 26137);
    final s = await app.search.search(SearchRequest.search('What is faith?'));
    expect(s.hits, hasLength(20));
    expect(s.profile, 'compass');
    // similar verses use the topic lane exactly when the host listed the (rights-gated) topics pack
    final hostHasTopics = File('${hosting.path}/bucket/topics-pack-v1.zip').existsSync();
    final sim = await app.search.search(SearchRequest.similar(26137, topK: 5));
    expect(sim.profile, hostHasTopics ? 'genome_topics_v1' : 'genome_weighted_cosine_v1');
    await app.close();
  }, timeout: const Timeout(Duration(minutes: 20)));
}
