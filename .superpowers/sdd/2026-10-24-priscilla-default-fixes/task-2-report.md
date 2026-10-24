# Task 2 implementation report

## Implemented

- `ensureData` now resolves a pretrial int8 pack from the explicit or conditional model preference for Priscilla, Apollos, and Aquila.
- The pretrial fallback applies only while `focusChoice` is null and skips an already-installed preferred model. Persisted trial choices, including `FocusVariant.none`, remain authoritative.
- Both the pretrial fallback and persisted-choice path honor Answer Focus Off and request no focus pack.
- `offerPriscillaDefaultSetup` now requires no explicit preference, no completed trial choice, no installed Answer Focus model, focus mode enabled, and no dismissal.
- The Home notice describes whether base scripture/search data remains or only Answer Focus remains, without an unverified size.
- Added a shared recording controller that overrides the existing host/download methods. Controller and widget tests inspect the real `RemotePack.kind` requests without network access.

## TDD evidence

- RED: `flutter test test/app_controller_focus_notice_test.dart` failed as expected because the recorded request contained only `release`, `engine`, `entities`, and `answers`, with no `priscilla-int8`.
- RED (Off paths): `flutter test test/app_controller_focus_notice_test.dart --plain-name "ensureData does not request"` failed because both the no-trial and persisted-choice cases still requested their focus packs while Off.
- GREEN: `flutter test test/app_controller_focus_notice_test.dart test/widget_test.dart` passed all 81 tests, including both Off paths.

## Full verification

- `flutter test`: 329 passed, 46 skipped, no failures.
- `git diff --check`: clean (apart from the repository's existing LF/CRLF warning for `test/widget_test.dart`).

## Files changed

- `lib/app_controller.dart`
- `lib/features/home/home_screen.dart`
- `test/app_controller_focus_notice_test.dart`
- `test/widget_test.dart`
- `test/fakes/recording_install_controller.dart`

## Self-review

- Confirmed all non-Ezra int8 pretrial models are covered.
- Confirmed completed `none` does not trigger the preference fallback.
- Confirmed Off blocks focus downloads both before a trial and for an existing persisted choice.
- Confirmed an installed preferred pack is not requested again.
- Confirmed no production test accessor or private-helper seam was added and widget tests do not use the network.
- Left the post-install conditional-default lifecycle issue unchanged for Task 3, as assigned.

## Concerns

None.
