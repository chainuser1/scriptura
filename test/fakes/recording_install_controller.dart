// The explicit forwarding keeps this fake's fixed-constructor intent obvious at each call site.
// ignore_for_file: use_super_parameters

import 'dart:io';

import 'package:scriptures_reader_mobile/app_controller.dart';
import 'package:scriptures_reader_mobile/data/content/content_repository.dart';
import 'package:scriptures_reader_mobile/data/user/user_store.dart';
import 'package:scriptures_reader_mobile/services/engine/downloader.dart';
import 'package:scriptures_reader_mobile/services/engine/search_service.dart';

class RecordingInstallController extends AppController {
  RecordingInstallController({
    required Directory root,
    UserStore? user,
    ContentRepository? repository,
    SearchService? search,
  }) : super.fixed(root: root, user: user, repository: repository, search: search);

  final requestedKinds = <String>[];

  static RemotePack _pack(String kind) => RemotePack(
        id: kind,
        kind: kind,
        title: kind,
        version: '1',
        folder: kind,
        optional: false,
        requires: const [],
        note: '',
        files: const [],
      );

  @override
  Future<RemoteIndex> checkHost(String base) async => RemoteIndex([
        for (final kind in [
          'release',
          'engine',
          'entities',
          'answers',
          'colbert',
          'answer-focus-int8',
          'answer-focus-fp16',
          'apollos-int8',
          'apollos-fp16',
          'priscilla-int8',
          'aquila-int8',
        ])
          _pack(kind),
      ]);

  @override
  Future<void> downloadAndInstall(
    String base,
    List<RemotePack> packs, {
    DownloadProgress? onProgress,
    bool Function()? isCancelled,
    void Function(RemotePack pack)? onPack,
  }) async {
    requestedKinds.addAll(packs.map((p) => p.kind));
  }
}
