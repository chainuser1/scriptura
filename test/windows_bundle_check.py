"""The Windows app folder must carry real copies of the engine's native libraries (the engine imports DirectML.dll
directly, so a missing or linked copy breaks all search on another PC).

  .venv\Scripts\python.exe -I test/windows_bundle_check.py   (after flutter build windows --release)
"""
from pathlib import Path

release = Path(__file__).resolve().parent.parent / 'build/windows/x64/runner/Release'
for name in ('scripture_engine.dll', 'DirectML.dll'):
    f = release / name
    assert f.exists(), f'{name} is missing from {release}'
    assert not f.is_symlink(), f'{name} is a link ({f.readlink()}); it would not exist on another PC'
    assert f.stat().st_size > 1_000_000, f'{name} is only {f.stat().st_size} bytes'
print('windows bundle: real engine libraries present')
