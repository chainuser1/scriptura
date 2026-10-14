"""Install the arm64 APK on a connected Android device, side-load the packs and run the on-device benchmark.

Needs: USB debugging enabled, the device authorised for this PC, generated-artifacts/{release,engine-pack,colbert-pack-v1}
and generated-artifacts/dist/app-release.apk (copy of the output of flutter build apk --release --target-platform android-arm64).

  .venv\\Scripts\\python.exe -I tool/android_device_run.py [--serial SERIAL] [--skip-push] [--no-colbert]

Writes local-benchmarks/android_benchmark.json (gitignored) and prints the gate summary of docs/ENGINE_PLAN.md E3.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADB = Path.home() / 'Android' / 'Sdk' / 'platform-tools' / 'adb.exe'
PKG = 'app.scriptura.reader'
APK = ROOT / 'generated-artifacts' / 'dist' / 'app-release.apk'  # copy of build/app/outputs/flutter-apk/app-release.apk


def adb(serial, *args, check=True, capture=True):
    cmd = [str(ADB)] + (['-s', serial] if serial else []) + list(args)
    r = subprocess.run(cmd, capture_output=capture, text=True)
    if check and r.returncode != 0:
        sys.exit(f'adb {" ".join(args)} failed:\n{r.stdout}\n{r.stderr}')
    return r.stdout.strip()


def remote_size(serial, path):
    r = subprocess.run([str(ADB), '-s', serial, 'shell', 'stat', '-c', '%s', path], capture_output=True, text=True)
    return int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip().isdigit() else -1


def push_tree(serial, src, dst, attempts=4):
    """File by file, skipping files already complete on the device and retrying a transport hiccup."""
    for f in sorted(p for p in src.rglob('*') if p.is_file()):
        target = f'{dst}/{f.relative_to(src).as_posix()}'
        if remote_size(serial, target) == f.stat().st_size:
            continue
        subprocess.run([str(ADB), '-s', serial, 'shell', 'mkdir', '-p', target.rsplit('/', 1)[0]], capture_output=True)
        for n in range(1, attempts + 1):
            r = subprocess.run([str(ADB), '-s', serial, 'push', str(f), target], capture_output=True, text=True)
            if r.returncode == 0 and remote_size(serial, target) == f.stat().st_size:
                break
            print(f'  retry {n}/{attempts}: {f.name}', flush=True)
            time.sleep(3)
        else:
            sys.exit(f'could not push {f}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--serial')
    ap.add_argument('--skip-push', action='store_true')
    ap.add_argument('--no-colbert', action='store_true')
    a = ap.parse_args()

    devices = [l.split()[0] for l in adb(None, 'devices').splitlines()[1:] if l.strip().endswith('device')]
    if not devices:
        sys.exit('No authorised Android device. Enable USB debugging, connect the phone and accept the prompt.')
    serial = a.serial or devices[0]
    model = adb(serial, 'shell', 'getprop', 'ro.product.model')
    abi = adb(serial, 'shell', 'getprop', 'ro.product.cpu.abi')
    release = adb(serial, 'shell', 'getprop', 'ro.build.version.release')
    mem = adb(serial, 'shell', 'grep', 'MemTotal', '/proc/meminfo')
    print(f'device {serial}: {model}, Android {release}, {abi}, {mem}')
    if abi != 'arm64-v8a':
        sys.exit(f'This build is arm64-v8a only; the device reports {abi}')
    if not APK.exists():
        sys.exit(f'APK not built: {APK}')

    print('installing APK...')
    adb(serial, 'install', '-r', str(APK))
    base = f'/sdcard/Android/data/{PKG}/files/dev-packs'
    if not a.skip_push:
        adb(serial, 'shell', 'mkdir', '-p', base)
        for src, dst in [('release', 'release'), ('engine-pack', 'engine-pack')] + ([] if a.no_colbert else [('colbert-pack-v1', 'colbert-pack-v1')]):
            path = ROOT / 'generated-artifacts' / src
            print(f'pushing {src} ({sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e9:.2f} GB)...', flush=True)
            push_tree(serial, path, f'{base}/{dst}')
    adb(serial, 'shell', 'rm', '-f', f'{base}/../benchmark.json')
    adb(serial, 'shell', f'echo 1 > {base}/run-benchmark')
    adb(serial, 'shell', 'am', 'force-stop', PKG)
    adb(serial, 'shell', 'monkey', '-p', PKG, '-c', 'android.intent.category.LAUNCHER', '1')
    print('benchmark running on the device (first launch installs the content release, then opens the engine)...', flush=True)

    out = None
    for _ in range(360):
        time.sleep(5)
        r = subprocess.run([str(ADB), '-s', serial, 'shell', 'cat', f'{base}/../benchmark.json'], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip().startswith('{'):
            out = r.stdout
            break
    if out is None:
        sys.exit('Timed out waiting for benchmark.json. Check: adb logcat -s flutter')
    res = json.loads(out)
    dest = ROOT / 'local-benchmarks'
    dest.mkdir(exist_ok=True)
    res['device'] = {'serial': serial, 'model': model, 'android': release, 'abi': abi, 'meminfo': mem}
    (dest / 'android_benchmark.json').write_text(json.dumps(res, indent=2), 'utf-8')
    print(json.dumps(res, indent=2))
    for prof in ('compass', 'lantern'):
        b = res.get(prof)
        if not b:
            continue
        w = b['warm_total_ms']
        ok = w['median'] <= 3000 and w['p95'] <= 6000 and b['cold']['first_query_ms'] <= 15000 and b['rss_mb_peak'] <= 2048
        print(f'{prof}: median {w["median"]:.0f} ms, p95 {w["p95"]:.0f} ms, cold {b["cold"]["first_query_ms"]} ms, '
              f'peak RSS {b["rss_mb_peak"]} MB -> {"PASS" if ok else "FAIL"} (gate 3000/6000/15000 ms, 2048 MB)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
