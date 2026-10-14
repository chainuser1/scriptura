"""Cross-compile the engine for Android arm64 and stage the shared libraries for the Gradle build.

Output (gitignored): android/app/src/main/jniLibs/arm64-v8a/{libscripture_engine.so, libonnxruntime.so, libc++_shared.so}
ONNX Runtime comes from the official onnxruntime-android AAR (version pinned to what the `ort` crate expects) and is
loaded at runtime (feature `dynamic-ort`).

  .venv\\Scripts\\python.exe -I tool/build_engine_android.py [--ndk PATH] [--api 24] [--ort 1.31.0]
"""
import argparse
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = 'aarch64-linux-android'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ndk', default=os.environ.get('ANDROID_NDK_HOME') or str(Path.home() / 'Android' / 'Sdk' / 'ndk' / '28.2.13676358'))
    ap.add_argument('--api', type=int, default=24)
    ap.add_argument('--ort', default='1.31.0')
    a = ap.parse_args()
    ndk = Path(a.ndk)
    host = 'windows-x86_64' if os.name == 'nt' else 'linux-x86_64'
    bin_dir = ndk / 'toolchains' / 'llvm' / 'prebuilt' / host / 'bin'
    ext = '.cmd' if os.name == 'nt' else ''
    clang = bin_dir / f'{TARGET}{a.api}-clang{ext}'
    if not clang.exists():
        sys.exit(f'NDK clang not found: {clang}')

    env = dict(os.environ)
    env['PATH'] = str(Path.home() / '.cargo' / 'bin') + os.pathsep + env['PATH']
    env['ANDROID_NDK_HOME'] = str(ndk)
    env['CARGO_TARGET_AARCH64_LINUX_ANDROID_LINKER'] = str(clang)
    env['CC_aarch64_linux_android'] = str(clang)
    env['AR_aarch64_linux_android'] = str(bin_dir / 'llvm-ar.exe' if os.name == 'nt' else bin_dir / 'llvm-ar')
    env['CFLAGS_aarch64_linux_android'] = '-fPIC'
    cargo = Path.home() / '.cargo' / 'bin' / ('cargo.exe' if os.name == 'nt' else 'cargo')
    subprocess.run([str(cargo), 'build', '--release', '--target', TARGET, '--no-default-features', '--features', 'dynamic-ort'],
                   cwd=ROOT / 'engine', env=env, check=True)

    out = ROOT / 'android' / 'app' / 'src' / 'main' / 'jniLibs' / 'arm64-v8a'
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / 'engine' / 'target' / TARGET / 'release' / 'libscripture_engine.so', out / 'libscripture_engine.so')

    aar = ROOT / '.artifact-staging' / f'onnxruntime-android-{a.ort}.aar'
    if not aar.exists():
        url = f'https://repo1.maven.org/maven2/com/microsoft/onnxruntime/onnxruntime-android/{a.ort}/onnxruntime-android-{a.ort}.aar'
        print('downloading', url)
        urllib.request.urlretrieve(url, aar)
    with zipfile.ZipFile(aar) as z:
        with z.open('jni/arm64-v8a/libonnxruntime.so') as src, open(out / 'libonnxruntime.so', 'wb') as dst:
            shutil.copyfileobj(src, dst)
    # the engine is Rust (no C++ runtime of its own) but onig and ONNX Runtime may need the shared libc++
    cxx = ndk / 'toolchains' / 'llvm' / 'prebuilt' / host / 'sysroot' / 'usr' / 'lib' / 'aarch64-linux-android' / 'libc++_shared.so'
    if cxx.exists():
        shutil.copy2(cxx, out / 'libc++_shared.so')
    for f in sorted(out.iterdir()):
        print(f'{f.name:28s}{f.stat().st_size:>12,}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
