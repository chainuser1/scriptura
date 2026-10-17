"""Stage a GitHub release: stable "latest" asset names, versioned copies, checksums and notes. Nothing is published.

GitHub serves  https://github.com/<owner>/<repo>/releases/latest/download/<asset>  for the newest release, but only if the
asset has the same file name in every release. So each release carries:

  Scriptura-Setup.exe            Windows installer
  Scriptura.apk                  Android package
  SHA256SUMS.txt                 checksums of the two files

File names never carry the version (owner's rule): the version is shown inside the app and in the release title.

and the app's update check reads  https://api.github.com/repos/<owner>/<repo>/releases/latest  (kReleasesApi).

  .venv\\Scripts\\python.exe -I tool/make_release.py [--notes "text"]

Prerequisite: tool/build_installer.py and `flutter build apk --release --target-platform android-arm64` have run, and
pubspec.yaml's version equals kAppVersion in lib/app/version.dart.
"""
import argparse
import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / 'generated-artifacts' / 'dist'
EXE = DIST / 'Scriptura-Setup.exe'  # written by tool/build_installer.py
APK = ROOT / 'build' / 'app' / 'outputs' / 'flutter-apk' / 'app-release.apk'  # written by flutter build apk


def _aapt():
    import os
    for sdk in (os.environ.get('ANDROID_HOME'), os.environ.get('ANDROID_SDK_ROOT'), Path.home() / 'Android' / 'Sdk',
                Path(os.environ.get('LOCALAPPDATA', '')) / 'Android' / 'Sdk'):
        tools = sorted((Path(sdk) / 'build-tools').glob('*/aapt.exe')) if sdk else []
        if tools:
            return tools[-1]
    sys.exit('aapt (Android SDK build-tools) not found; it is needed to read the APK version')


def apk_version(apk):
    """(versionName, versionCode) recorded in the APK."""
    out = subprocess.run([str(_aapt()), 'dump', 'badging', str(apk)], capture_output=True, text=True).stdout
    m = re.search(r"versionCode='(\d+)' versionName='([^']+)'", out)
    if not m:
        sys.exit(f'could not read the version of {apk}')
    return m.group(2), m.group(1)


def exe_version(exe):
    """Product version recorded in the Windows installer."""
    out = subprocess.run(['powershell', '-NoProfile', '-Command', f"(Get-Item '{exe}').VersionInfo.ProductVersion"],
                         capture_output=True, text=True).stdout
    return out.strip()


def check_package_versions(version, apk, exe):
    """Exits unless each given package was built for [version] (a stale copy once shipped as two releases)."""
    if apk is not None and apk_version(apk)[0] != version:
        sys.exit(f'{apk} is version {apk_version(apk)[0]}, not {version}: rebuild it (flutter build apk --release)')
    if exe is not None and exe_version(exe) != version:
        sys.exit(f'{exe} is version {exe_version(exe)}, not {version}: rebuild it (tool/build_installer.py)')


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 22), b''):
            h.update(c)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--notes', default='', help='release notes; the last commit subjects are appended')
    a = ap.parse_args()

    version = re.search(r'^version:\s*([0-9][0-9.]*)', (ROOT / 'pubspec.yaml').read_text('utf-8'), re.M).group(1)
    code = re.search(r"kAppVersion\s*=\s*'([^']+)'", (ROOT / 'lib' / 'app' / 'version.dart').read_text('utf-8')).group(1)
    if version != code:
        sys.exit(f'pubspec.yaml says {version} but lib/app/version.dart says {code}; make them equal and rebuild')
    exe, apk = EXE, APK
    for f in (exe, apk):
        if not f.exists():
            sys.exit(f'missing {f}: build it first')
    check_package_versions(version, apk, exe)

    out = ROOT / 'generated-artifacts' / 'release-assets' / version
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    names = {
        'Scriptura-Setup.exe': exe,
        'Scriptura.apk': apk,
    }
    for name, src in names.items():
        shutil.copy2(src, out / name)
    sums = '\n'.join(f'{sha256(out / n)}  {n}' for n in sorted(names)) + '\n'
    (out / 'SHA256SUMS.txt').write_text(sums, 'utf-8')

    log = subprocess.run(['git', 'log', '--pretty=- %s', '-n', '15'], cwd=ROOT, capture_output=True, text=True).stdout
    notes = f'# Scriptura {version}\n\n{a.notes}\n\n## Changes\n{log}\n## Downloads\n' \
            '- Windows: `Scriptura-Setup.exe` (per-user installer, unsigned)\n- Android: `Scriptura.apk` (arm64)\n' \
            '- Checksums: `SHA256SUMS.txt`\n\nOn first run the app downloads its scripture text and search data itself; ' \
            'nothing is bundled.\n'
    (out / 'RELEASE_NOTES.md').write_text(notes, 'utf-8')

    print(f'staged {out}')
    for p in sorted(out.iterdir()):
        print(f'  {p.stat().st_size / 1e6:8.1f} MB  {p.name}')
    print(f"""
publish (from a clone with a GitHub remote; needs the GitHub CLI `gh`):

  git tag v{version}
  git push origin v{version}
  gh release create v{version} "{out}\\*" --title "Scriptura {version}" --notes-file "{out / 'RELEASE_NOTES.md'}" --latest

stable links afterwards:
  https://github.com/<owner>/<repo>/releases/latest/download/Scriptura-Setup.exe
  https://github.com/<owner>/<repo>/releases/latest/download/Scriptura.apk
  https://api.github.com/repos/<owner>/<repo>/releases/latest   (set as kReleasesApi in lib/app/version.dart)""")
    return 0


if __name__ == '__main__':
    sys.exit(main())
