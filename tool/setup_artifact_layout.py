"""Keep large, generated and quarantined files OUT of the project folder.

The repository holds source, docs and small goldens only. Everything big lives in one artifacts root next to the
original data (default: ../scriptura/artifacts) and is reached through directory junctions that keep the paths every
tool already uses:

  <repo>/generated-artifacts  ->  <root>/generated      release/, engine-pack/, colbert-pack-v1/, onnx-*, dist/
  <repo>/.artifact-staging    ->  <root>/staging        import-application-v1/extracted, validation caches
  <repo>/engine/target        ->  <root>/cargo-target   Rust build output

It also removes what no longer matters, but only after proving it is reproducible or duplicated:
  * staged archives and database copies that are byte-identical to the originals in ../scriptura
    (databases become a junction to the originals, which every tool opens read-only)
  * legacy files classed 'discard' or 'archive' in docs/legacy_disposition.json that are byte-identical to the
    phase-0 backup in ../scriptura/app-backups
  * the FP32 ONNX export (regenerate with tool/export_onnx.py), the ONNX Runtime AAR (re-downloaded by
    tool/build_engine_android.py), Flutter build/ output

Dry run by default.

  .venv\\Scripts\\python.exe -I tool/setup_artifact_layout.py [--apply] [--root PATH]
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORIGINALS = ROOT.parent / 'scriptura'
BACKUP = ORIGINALS / 'app-backups' / 'scriptures_reader_mobile-before-phase0-20261011'


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 23), b''):
            h.update(c)
    return h.hexdigest()


def size_of(p):
    p = Path(p)
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob('*') if f.is_file())


def is_junction(p):
    return os.path.isdir(p) and bool(os.stat(p, follow_symlinks=False).st_file_attributes & 0x400) if os.name == 'nt' else Path(p).is_symlink()


class Plan:
    def __init__(self, apply):
        self.apply = apply
        self.freed = 0
        self.log = []

    def say(self, msg):
        print(msg, flush=True)

    def delete(self, path, why):
        path = Path(path)
        if not path.exists() and not path.is_symlink():
            return
        n = size_of(path) if not is_junction(path) else 0
        self.freed += n
        self.say(f'  delete {path.relative_to(ROOT) if ROOT in path.parents else path}  ({n / 1e6:,.0f} MB)  -- {why}')
        if self.apply:
            if is_junction(path):
                os.rmdir(path)
            elif path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()

    def move(self, src, dst):
        src, dst = Path(src), Path(dst)
        if is_junction(src) or not src.exists():
            return
        if dst.exists():
            sys.exit(f'refusing to merge: {dst} already exists')
        self.say(f'  move   {src.relative_to(ROOT)}  ->  {dst}')
        if self.apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.replace(src, dst)

    def junction(self, link, target):
        link, target = Path(link), Path(target)
        if link.exists() or is_junction(link):
            return
        self.say(f'  link   {link.relative_to(ROOT)}  =>  {target}')
        if self.apply:
            target.mkdir(parents=True, exist_ok=True)
            subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)], check=True, capture_output=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--root', default=str(ORIGINALS / 'artifacts'))
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    art = Path(a.root)
    plan = Plan(a.apply)
    print(('APPLYING' if a.apply else 'DRY RUN') + f' -> artifacts root {art}\n')

    gen, stg, leg = ROOT / 'generated-artifacts', ROOT / '.artifact-staging', ROOT / 'legacy-quarantine'
    imp = stg / 'import-application-v1'

    print('1. duplicates of the originals (verified by SHA-256)')
    if imp.exists() and not is_junction(imp / 'databases'):
        for z in sorted((imp / 'archives').glob('*')):
            o = ORIGINALS / z.name
            if not (o.exists() and o.stat().st_size == z.stat().st_size and sha(o) == sha(z)):
                sys.exit(f'{z.name} is not identical to its original; refusing to delete')
        for d in sorted((imp / 'databases').glob('*')):
            o = ORIGINALS / 'application_databases' / d.name
            if not (o.exists() and o.stat().st_size == d.stat().st_size and sha(o) == sha(d)):
                sys.exit(f'{d.name} is not identical to its original; refusing to delete')
        plan.delete(imp / 'archives', 'identical to the zips in ../scriptura')
        plan.delete(imp / 'databases', 'identical to ../scriptura/application_databases (replaced by a junction)')
        if a.apply:
            subprocess.run(['cmd', '/c', 'mklink', '/J', str(imp / 'databases'), str(ORIGINALS / 'application_databases')],
                           check=True, capture_output=True)

    print('2. legacy files that are discarded or archived (present byte-identical in the phase-0 backup)')
    disp = json.loads((ROOT / 'docs' / 'legacy_disposition.json').read_text('utf-8'))
    for f in disp['files']:
        if f['class'] not in ('discard', 'archive'):
            continue
        p = leg / 'resources' / f['path']
        if not p.exists():
            continue
        cands = [c for c in BACKUP.rglob(Path(f['path']).name)  # layout differs from quarantine; match by name, size, hash
                  if c.is_file() and c.stat().st_size == f['bytes']]
        if not any(sha(c) == f['sha256'] for c in cands):
            print(f'  KEEP {f["path"]}: not found byte-identical in the backup')
            continue
        plan.delete(p, f'{f["class"]}: {f["reason"][:60]}')

    print('3. reproducible intermediates and build output')
    plan.delete(gen / 'onnx-fp32', 'regenerate with tool/export_onnx.py')
    plan.delete(stg / 'onnxruntime-android-1.31.0.aar', 're-downloaded by tool/build_engine_android.py')
    plan.delete(ROOT / 'build', 'Flutter build output (flutter build ...)')

    print('4. move what remains into the artifacts root and link it back')
    for repo_path, name in [(gen, 'generated'), (stg, 'staging'), (ROOT / 'engine' / 'target', 'cargo-target')]:
        plan.move(repo_path, art / name)
        plan.junction(repo_path, art / name)

    print(f'\n{"freed" if a.apply else "would free"} about {plan.freed / 1e9:.2f} GB; the project folder keeps only source, docs and goldens')
    if not a.apply:
        print('Re-run with --apply to perform it.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
