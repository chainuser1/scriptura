r"""tool/make_release.py must never stage a package built for another version (1.0.4 and 1.0.5 shipped a 1.0.3 APK
because it read a stale copy). Uses the APKs and installer on this machine; skips what is not there.

  .venv\Scripts\python.exe -I test/make_release_check.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
import make_release as mr  # noqa: E402

built = ROOT / 'build/app/outputs/flutter-apk/app-release.apk'
stale = ROOT / 'generated-artifacts/dist/app-release.apk'
assert mr.APK == built, f'the release must take the APK Flutter just built, not {mr.APK}'

if built.exists():
    name, code = mr.apk_version(built)
    assert name and code.isdigit(), (name, code)
    mr.check_package_versions(name, mr.APK, mr.EXE if mr.EXE.exists() else None)  # same version: no error
    try:
        mr.check_package_versions('9.9.9', built, None)
        raise AssertionError('an APK for another version must be refused')
    except SystemExit as e:
        assert '9.9.9' in str(e) and name in str(e), e

if stale.exists() and built.exists() and mr.apk_version(stale) != mr.apk_version(built):
    try:
        mr.check_package_versions(mr.apk_version(built)[0], stale, None)
        raise AssertionError('the stale dist APK must be refused')
    except SystemExit:
        pass

if mr.EXE.exists():
    v = mr.exe_version(mr.EXE)
    assert v.count('.') == 2, v
    try:
        mr.check_package_versions('9.9.9', None, mr.EXE)
        raise AssertionError('an installer for another version must be refused')
    except SystemExit as e:
        assert '9.9.9' in str(e), e

print('make_release: packages are checked against the version')
