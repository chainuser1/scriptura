"""Guard: every legacy resource file is classified, nothing legacy is a runtime source.
Run: .venv\\Scripts\\python.exe -I test/legacy_disposition_check.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
manifest = json.loads((ROOT / 'docs' / 'legacy_disposition.json').read_text('utf-8'))
files = manifest['files']

assert files, 'empty manifest'
assert {f['class'] for f in files} <= {'required_pack', 'optional_pack', 'archive', 'discard'}
assert all(f['reason'] for f in files), 'every entry needs a reason'
assert not [f for f in files if f['class'] in ('required_pack', 'optional_pack') and not f['pack']], 'pack classes need a pack name'
assert len({f['path'] for f in files}) == len(files), 'duplicate paths'

by_path = {f['path']: f for f in files}
assert by_path['db/lds-scriptures-sqlite.db']['class'] == 'required_pack', 'KJV is the default English display edition (D1)'
assert by_path['db/japanese-scriptures-sqlite.db']['class'] == 'discard', 'Japanese is excluded (D6)'

discard = {f['path'] for f in files if f['class'] == 'discard'}
for must in ('db/verse-embeddings.db', 'db/verse-graph.db', 'db/search-graph.db',
             'db/concept-embeddings.db', 'models/scripture-bge/onnx/model_quantized.onnx'):
    assert must in discard, f'{must} must be discard'

known = {f['path']: f['bytes'] for f in files}
for base in (ROOT / 'assets' / 'resources', ROOT / 'legacy-quarantine' / 'resources'):
    if base.exists():
        for p in base.rglob('*'):
            if p.is_file():
                rel = p.relative_to(base).as_posix()
                assert rel in known, f'unclassified legacy file: {rel}'
                assert p.stat().st_size == known[rel], f'size changed: {rel}'
print('legacy disposition: OK,', len(files), 'files')
