"""One reproducible command that builds the whole reading-pack release.

  base scriptures_genome.db (pinned, never modified) + legacy KJV/LDS text + catalog data
    -> KJV-switched intermediate (v1 shape, temporary)
    -> catalog.db                      verse-ID ranges, per-language names and aliases
    -> content.db  (schema v2)         compact text-only tables + provenance ranges
    -> phrase-index.db                 FTS5 per served language
    -> manifest.json                   sizes, SHA-256, verse-order contract, edition and source identities

  .venv\\Scripts\\python.exe -I tool/build_release.py OUT_DIR \\
      --base C:\\...\\application_databases\\scriptures_genome.db --legacy-lds LDS.db \\
      --legacy-lang spanish=PATH --legacy-lang tagalog=PATH --legacy-lang cebuano=PATH --legacy-lang greek=PATH
"""
import argparse
import gc
import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_catalog_db  # noqa: E402
import build_content_v2  # noqa: E402
import build_kjv_content_db  # noqa: E402
import phrase_search  # noqa: E402

DATA = Path(__file__).resolve().parent / 'data'


def _sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 22), b''):
            h.update(chunk)
    return h.hexdigest()


def build_release(base_db, legacy_lds, legacy_lang, out_dir, manual=None, aliases=None):
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise FileExistsError(out_dir)
    manual = manual if manual is not None else json.loads((DATA / 'catalog_manual.json').read_text('utf-8'))
    aliases = aliases if aliases is not None else json.loads((DATA / 'book_aliases_en.json').read_text('utf-8'))
    work = out_dir.with_name(out_dir.name + '.work')
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    try:
        kjv = build_kjv_content_db.build(base_db, legacy_lds, work / 'kjv')
        kjv_db = work / 'kjv' / 'scriptures_genome.db'
        catalog_tmp = work / 'catalog.db'
        cat = build_catalog_db.build(kjv_db, catalog_tmp, legacy_lds, legacy_lang, manual, aliases)
        out_dir.mkdir(parents=True)
        content = build_content_v2.build(kjv_db, catalog_tmp, out_dir / 'content.db')
        shutil.copyfile(catalog_tmp, out_dir / 'catalog.db')
        phrase = phrase_search.build_index(kjv_db, out_dir / 'phrase-index.db')

        groups = {'content.db': 'reading', 'catalog.db': 'reading', 'phrase-index.db': 'reading'}
        files = {n: {'bytes': (out_dir / n).stat().st_size, 'sha256': _sha(out_dir / n), 'group': g} for n, g in groups.items()}
        manifest = {
            'release': f"{kjv['manifest']['release']}",
            'schema': 2,
            'files': files,
            'content_contract': {'verse_order_sha256': cat['verse_order_sha256']},
            'english_text_edition': 'kjv-lds',
            'served_languages': cat['languages'],
            'sources': {
                'base_scriptures_genome_sha256': _sha(base_db),
                'legacy_lds_sha256': _sha(legacy_lds),
                'catalog_manual_sha256': hashlib.sha256(json.dumps(manual, sort_keys=True).encode()).hexdigest(),
                'tool': 'tool/build_release.py',
            },
            'rows': content['languages'],
        }
        (out_dir / 'manifest.json').write_text(json.dumps(manifest, indent=1, ensure_ascii=False), 'utf-8')
    except BaseException:
        shutil.rmtree(out_dir, ignore_errors=True)
        raise
    finally:
        gc.collect()  # drop any lingering SQLite handles (Windows cannot delete open files)
        shutil.rmtree(work, ignore_errors=True)
    if work.exists():
        raise RuntimeError(f'could not remove work directory {work}')
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('out_dir')
    ap.add_argument('--base', required=True)
    ap.add_argument('--legacy-lds', required=True)
    ap.add_argument('--legacy-lang', action='append', default=[])
    a = ap.parse_args()
    m = build_release(a.base, a.legacy_lds, dict(x.split('=', 1) for x in a.legacy_lang), a.out_dir)
    total = sum(f['bytes'] for f in m['files'].values())
    print(f"release {m['release']}: " + ', '.join(f"{n} {f['bytes'] / 1e6:.1f} MB" for n, f in m['files'].items()) + f" | total {total / 1e6:.1f} MB")
    return 0


if __name__ == '__main__':
    sys.exit(main())
