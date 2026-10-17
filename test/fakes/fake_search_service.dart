import 'dart:async';

import 'package:scriptures_reader_mobile/services/engine/search_models.dart';
import 'package:scriptures_reader_mobile/services/engine/search_service.dart';

/// Scriptable search backend: each call is answered by [handler], optionally after the returned future completes,
/// so tests can hold a request open to exercise cancellation and stale-result handling.
class FakeSearchService implements SearchService {
  FakeSearchService(this.handler, {this.colbert = true, this.hasFocus = false});
  final Future<SearchResponse> Function(SearchRequest request, int requestId) handler;
  final bool colbert;
  @override
  final bool hasFocus;
  final requests = <SearchRequest>[];
  final cancelled = <int>[];
  int _next = 0;

  @override
  bool get available => true;
  @override
  String? get unavailableReason => null;
  @override
  bool get hasColbertPack => colbert;
  @override
  int nextRequestId() => ++_next;

  @override
  Future<SearchResponse> search(SearchRequest request, {int? requestId}) {
    requests.add(request);
    return handler(request, requestId ?? nextRequestId());
  }

  @override
  void cancel(int requestId) => cancelled.add(requestId);
  @override
  Future<void> close() async {}
}

SearchResponse semantic(List<int> ids, {PersonInterpretation? person, String profile = 'compass', String? requested}) =>
    SearchResponse(
      mode: 'semantic',
      hits: [for (var i = 0; i < ids.length; i++) Hit(ids[i], 10.0 - i)],
      person: person,
      profile: profile,
      requestedProfile: requested ?? profile,
      configurationId: 'a' * 64,
    );
