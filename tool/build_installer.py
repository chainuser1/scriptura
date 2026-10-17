"""Build the Windows installer (Scriptura-Setup.exe; the version is inside the app, not in the file name).

Steps: cargo build --release (engine DLL), flutter build windows --release, then Inno Setup (installer/scriptures.iss).
Output goes to generated-artifacts/dist/. The installer is unsigned: Windows SmartScreen will warn until it is signed
with a code-signing certificate (set SIGNTOOL in the environment to sign the executable and installer yourself).

  .venv\\Scripts\\python.exe -I tool/build_installer.py [--skip-build]
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RELEASE = ROOT / 'build' / 'windows' / 'x64' / 'runner' / 'Release'
ISCC = Path(os.environ.get('ISCC') or Path.home() / 'AppData' / 'Local' / 'Programs' / 'Inno Setup 6' / 'ISCC.exe')  # CI sets ISCC
CARGO = Path.home() / '.cargo' / 'bin' / 'cargo.exe'


def run(cmd, **kw):
    print('>', ' '.join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--skip-build', action='store_true')
    a = ap.parse_args()
    version = re.search(r'^version:\s*([0-9.]+)', (ROOT / 'pubspec.yaml').read_text('utf-8'), re.M).group(1)
    if not a.skip_build:
        run([CARGO, 'build', '--release'], cwd=ROOT / 'engine')
        run(['flutter.bat', 'build', 'windows', '--release'], cwd=ROOT)
    if not (RELEASE / 'Scriptura.exe').exists():
        sys.exit(f'{RELEASE / "Scriptura.exe"} not found')
    if not (RELEASE / 'scripture_engine.dll').exists():
        sys.exit('scripture_engine.dll is not in the release folder; build the engine first')
    dml = RELEASE / 'DirectML.dll'  # imported by the engine; a link into the build cache would not exist on another PC
    if not dml.exists() or dml.is_symlink() or dml.stat().st_size < 1_000_000:
        sys.exit('DirectML.dll is missing or a link in the release folder; rebuild with flutter build windows --release')
    out = ROOT / 'generated-artifacts' / 'dist'
    out.mkdir(parents=True, exist_ok=True)
    run([ISCC, f'/DSourceDir={RELEASE}', f'/DAppVersion={version}', f'/DSourceRoot={ROOT}', f'/DOutputDir={out}',
         f'/DIconFile={ROOT / "windows" / "runner" / "resources" / "app_icon.ico"}', ROOT / 'installer' / 'scriptures.iss'])
    exe = out / 'Scriptura-Setup.exe'
    print(f'{exe}  {exe.stat().st_size / 1e6:.1f} MB')
    return 0


if __name__ == '__main__':
    sys.exit(main())
