"""Write the single bucket-root index the app reads, and zip the content release if needed. Nothing is uploaded.

Inputs (made by tool/prepare_hosting.py, plus the pack zips beside them):
  hosting/search-data/{index.json, engine-pack-v1.zip, colbert-pack-v1.zip}
  hosting/content/{index.json, <release>/...}

Output: hosting/bucket/index.json  and  hosting/bucket/scripture-content-v1.zip
Upload index.json and the zips in that folder next to the existing engine-pack-v1.zip / colbert-pack-v1.zip. Each pack entry gains an
`archive` (name, size, SHA-256 of the zip); `files` still lists what must exist after unpacking.

  .venv\\Scripts\\python.exe -I tool/make_bucket_index.py [--root ../scriptura/artifacts]
"""
import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 22), b''):
            h.update(c)
    return h.hexdigest()


def archive_entry(path):
    return {'name': path.name, 'bytes': path.stat().st_size, 'sha256': sha256(path)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--root', default=str(ROOT.parent / 'scriptura' / 'artifacts'))
    ap.add_argument('--include-topics', action='store_true',
                    help='also list the rights-gated topics pack (verse-to-topic map from a Church-compiled index); off by default')
    a = ap.parse_args()
    hosting = Path(a.root) / 'hosting'
    out = hosting / 'bucket'
    out.mkdir(exist_ok=True)

    search = json.loads((hosting / 'search-data' / 'index.json').read_text('utf-8'))
    content = json.loads((hosting / 'content' / 'index.json').read_text('utf-8'))
    packs = []

    # content: zip the release folder (top-level folder = pack folder, as the other archives have)
    rel = content['packs'][0]
    zpath = out / 'scripture-content-v1.zip'
    src = hosting / 'content' / rel['folder']
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for rel_name in rel['files']:
            z.write(src / rel_name, f'{rel["folder"]}/{rel_name}')
    rel['archive'] = archive_entry(zpath)
    packs.append(rel)

    for p in search['packs']:
        z = hosting / 'search-data' / f'{p["folder"]}.zip'
        if not z.exists():
            sys.exit(f'missing {z}')
        with zipfile.ZipFile(z) as zf:
            names = {n.split('/', 1)[1] for n in zf.namelist() if '/' in n and not n.endswith('/')}
        missing = set(p['files']) - names
        if missing:
            sys.exit(f'{z.name} lacks {sorted(missing)[:3]}')
        p['archive'] = archive_entry(z)
        packs.append(p)

    # small project-built packs (names of people and places, study questions): zipped here, listed as required
    extras = [('entities-pack-v1', 'entities', 'Names of people and places', 'Understands who and where you ask about.'),
              ('answers-pack-v1', 'answers', 'Study questions', 'Questions a passage speaks to, in your language.')]
    if a.include_topics:
        extras.append(('topics-pack-v1', 'topics', 'Topic index', 'Sharper similar verses.'))
    # Answer focus (tool/build_answer_focus_pack.py): optional; a device downloads only the variant it chose
    optional = {'answer-focus-int8-v1', 'answer-focus-fp16-v1'}
    extras += [('answer-focus-int8-v1', 'answer-focus-int8', 'Answer focus', 'Puts the passages that answer your question first.'),
               ('answer-focus-fp16-v1', 'answer-focus-fp16', 'Answer focus (graphics)', 'Puts the passages that answer your question first.')]
    for pid, kind, title, note in extras:
        src = ROOT / 'generated-artifacts' / pid
        manifest = json.loads((src / 'manifest.json').read_text('utf-8'))
        z = out / f'{pid}.zip'
        with zipfile.ZipFile(z, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for name in list(manifest['files']) + ['manifest.json']:
                zf.write(src / name, f'{pid}/{name}')
        files = {n: {'bytes': m['bytes'], 'sha256': m['sha256']} for n, m in manifest['files'].items()}
        mf = src / 'manifest.json'
        files['manifest.json'] = {'bytes': mf.stat().st_size, 'sha256': sha256(mf)}
        packs.append({'id': pid, 'kind': kind, 'title': title, 'version': '1', 'folder': pid, 'optional': pid in optional, 'requires': [],
                      'note': note, 'bytes': sum(f['bytes'] for f in files.values()), 'files': files, 'archive': archive_entry(z)})

    (out / 'index.json').write_text(json.dumps({'format': 'scriptura-index-v1', 'generated': search['generated'], 'packs': packs}, indent=1), 'utf-8')
    for p in packs:
        print(f'{p["id"]:22s} {p["archive"]["name"]:30s} {p["archive"]["bytes"] / 1e6:9.1f} MB  {p["archive"]["sha256"][:12]}')
    print(f'\nupload from {out}: index.json (replace) and scripture-content-v1.zip (new)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
