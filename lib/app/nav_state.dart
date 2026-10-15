import 'package:flutter/foundation.dart';

enum Dest { home, read, search, study, settings }

enum SearchMode { meaning, phrase }

/// A search someone asked for from outside the search screen (Home, the command bar, a verse action).
class PendingSearch {
  PendingSearch.text(this.query, {this.mode = SearchMode.meaning})
      : similarTo = null,
        person = null;
  PendingSearch.similar(int verseId, this.query)
      : similarTo = verseId,
        mode = SearchMode.meaning,
        person = null;
  final String query;
  final SearchMode mode;
  final int? similarTo;
  final String? person;
}

/// Where the user is. Screens read this and call its methods; nothing else coordinates navigation.
class NavState extends ChangeNotifier {
  Dest dest = Dest.home;
  int? bookId;
  int chapter = 1;

  /// Verse to mark in the reading view (set when arriving from a search result, bookmark or note).
  int? verse;
  PendingSearch? pending;

  /// True while the Trail page is on screen; the return bar hides itself then.
  bool trailOpen = false;

  void setTrailOpen(bool open) {
    if (trailOpen == open) return;
    trailOpen = open;
    notifyListeners();
  }

  void go(Dest d) {
    if (dest == d) return;
    dest = d;
    notifyListeners();
  }

  void openChapter(int book, int chapterNumber, {int? verseNumber}) {
    bookId = book;
    chapter = chapterNumber;
    verse = verseNumber;
    dest = Dest.read;
    notifyListeners();
  }

  /// Chapter changes inside the reader do not switch destination.
  void setChapter(int book, int chapterNumber) {
    bookId = book;
    chapter = chapterNumber;
    verse = null;
    notifyListeners();
  }

  void ask(String query, {SearchMode mode = SearchMode.meaning}) {
    pending = PendingSearch.text(query, mode: mode);
    dest = Dest.search;
    notifyListeners();
  }

  void askSimilar(int verseId, String label) {
    pending = PendingSearch.similar(verseId, label);
    dest = Dest.search;
    notifyListeners();
  }

  PendingSearch? takePending() {
    final p = pending;
    pending = null;
    return p;
  }
}
