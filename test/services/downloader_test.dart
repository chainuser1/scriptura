import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/services/engine/downloader.dart';
import 'package:scriptures_reader_mobile/services/engine/engine_pack.dart';

/// A tiny static host with Range support, to exercise the downloader without a network.
class _Host {
  _Host(this.files);
  final Map<String, List<int>> files;
  late final HttpServer server;
  int requests = 0;
  int? dropAfter; // cut the next response short after this many bytes (simulated interruption)
  final seenRanges = <String?>[];

  Future<Uri> start() async {
    server = await HttpServer.bind('127.0.0.1', 0);
    server.listen((req) async {
      requests++;
      final path = req.uri.path.substring(1);
      final data = files[path];
      if (data == null) {
        req.response.statusCode = 404;
        await req.response.close();
        return;
      }
      final range = req.headers.value(HttpHeaders.rangeHeader);
      seenRanges.add(range);
      var start = 0;
      if (range != null) {
        start = int.parse(range.substring('bytes='.length).split('-').first);
        req.response.statusCode = 206;
      }
      var body = data.sublist(start);
      final cut = dropAfter;
      if (cut != null) {
        dropAfter = null;
        req.response.contentLength = body.length;
        final socket = await req.response.detachSocket(writeHeaders: true);
        socket.add(body.sublist(0, cut));
        await socket.flush();
        socket.destroy();
        return;
      }
      req.response.contentLength = body.length;
      req.response.add(body);
      await req.response.close();
    });
    return Uri.parse('http://127.0.0.1:${server.port}/');
  }

  Future<void> stop() => server.close(force: true);
}

RemotePack packFor(Map<String, List<int>> files, {String folder = 'engine-pack-v1'}) => RemotePack(
      id: folder,
      kind: 'engine',
      title: 'Search data',
      version: '1',
      folder: folder,
      optional: false,
      requires: const [],
      note: '',
      files: [for (final e in files.entries) RemoteFile(e.key, e.value.length, sha256.convert(e.value).toString())],
    );

void main() {
  late Directory tmp;
  setUp(() => tmp = Directory.systemTemp.createTempSync('dl-'));
  tearDown(() => tmp.deleteSync(recursive: true));

  final big = List<int>.generate(300000, (i) => i % 251);
  final small = utf8.encode('{"format":"engine-pack-v1","files":{}}');

  test('downloads every file, verified, with progress', () async {
    final host = _Host({'engine-pack-v1/a.bin': big, 'engine-pack-v1/manifest.json': small});
    final base = await host.start();
    addTearDown(host.stop);
    final pack = packFor({'a.bin': big, 'manifest.json': small});
    var last = 0;
    final dir = await PackDownloader().download(base, pack, Directory('${tmp.path}/work'), onProgress: (d, t, f) => last = d);
    expect(last, big.length + small.length);
    expect(File('${dir.path}/a.bin').readAsBytesSync(), big);
  });

  test('an interrupted download resumes from the bytes already on disk', () async {
    final host = _Host({'engine-pack-v1/a.bin': big})..dropAfter = 100000;
    final base = await host.start();
    addTearDown(host.stop);
    final pack = packFor({'a.bin': big});
    final work = Directory('${tmp.path}/work');
    final dl = PackDownloader();
    await expectLater(dl.download(base, pack, work), throwsA(anything)); // connection cut mid-file
    expect(File('${work.path}/engine-pack-v1/a.bin.part').lengthSync(), greaterThan(0));
    await dl.download(base, pack, work);
    expect(host.seenRanges.last, startsWith('bytes='));
    expect(File('${work.path}/engine-pack-v1/a.bin').readAsBytesSync(), big);
  });

  test('a corrupted download is rejected and discarded', () async {
    final bad = [...big]..[10] = 99;
    final host = _Host({'engine-pack-v1/a.bin': bad});
    final base = await host.start();
    addTearDown(host.stop);
    final pack = packFor({'a.bin': big}); // index promises the good hash
    await expectLater(PackDownloader().download(base, pack, Directory('${tmp.path}/work')),
        throwsA(isA<PackException>().having((e) => e.code, 'code', 'hash_mismatch')));
    expect(File('${tmp.path}/work/engine-pack-v1/a.bin').existsSync(), isFalse);
    expect(File('${tmp.path}/work/engine-pack-v1/a.bin.part').existsSync(), isFalse);
  });

  test('a finished file is not downloaded again', () async {
    final host = _Host({'engine-pack-v1/a.bin': big});
    final base = await host.start();
    addTearDown(host.stop);
    final pack = packFor({'a.bin': big});
    final work = Directory('${tmp.path}/work');
    await PackDownloader().download(base, pack, work);
    final before = host.requests;
    await PackDownloader().download(base, pack, work);
    expect(host.requests, before);
  });

  test('a missing file and a cancel are reported distinctly', () async {
    final host = _Host({});
    final base = await host.start();
    addTearDown(host.stop);
    final pack = packFor({'a.bin': big});
    await expectLater(PackDownloader().download(base, pack, Directory('${tmp.path}/w1')),
        throwsA(isA<PackException>().having((e) => e.code, 'code', 'download_failed')));
    await expectLater(PackDownloader().download(base, pack, Directory('${tmp.path}/w2'), isCancelled: () => true),
        throwsA(isA<PackException>().having((e) => e.code, 'code', 'cancelled')));
  });

  test('index parsing: a foreign document and bad addresses are refused', () {
    expect(() => RemoteIndex.parse('{"hello":1}'), throwsA(isA<PackException>()));
    expect(() => PackDownloader.normalize('ftp://x'), throwsA(isA<PackException>()));
    expect(PackDownloader.normalize('https://huggingface.co/u/r/resolve/main').toString(), 'https://huggingface.co/u/r/resolve/main/');
    final idx = RemoteIndex.parse(jsonEncode({
      'format': 'scriptura-index-v1',
      'packs': [
        {
          'id': 'p', 'kind': 'engine', 'title': 'T', 'version': 1, 'folder': 'p', 'optional': false, 'requires': [], 'note': '',
          'files': {'a': {'bytes': 3, 'sha256': 'x'}}
        }
      ]
    }));
    expect(idx.packs.single.bytes, 3);
  });

  test('adoptVerified activates a staged pack and removes bookkeeping files', () async {
    final staged = Directory('${tmp.path}/staged')..createSync();
    File('${staged.path}/manifest.json').writeAsStringSync(jsonEncode({
      'format': 'engine-pack-v1',
      'files': {'a.bin': {'bytes': 3, 'sha256': 'x'}}
    }));
    File('${staged.path}/a.bin').writeAsBytesSync([1, 2, 3]);
    File('${staged.path}/a.bin.ok').writeAsStringSync('x');
    final store = PackStore(Directory('${tmp.path}/app'), PackKind.engine);
    final p = await store.adoptVerified(staged);
    expect(p.has('a.bin'), isTrue);
    expect(p.has('a.bin.ok'), isFalse);
    expect(store.active(), isNotNull);
  });
}
