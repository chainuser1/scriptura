import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
from check_data_sources import check  # noqa: E402

# 1) a synthetic project that references legacy resources is flagged
bad = Path(tempfile.mkdtemp())
(bad / 'lib').mkdir()
(bad / 'lib' / 'x.dart').write_text("final p = 'assets/resources/db/verse-embeddings.db';\n", 'utf-8')
(bad / 'pubspec.yaml').write_text('flutter:\n  assets:\n    - assets/resources/\n', 'utf-8')
v = check(bad)
assert any('x.dart' in s for s in v), v
assert any('pubspec.yaml' in s for s in v), v

# 2) the real project is clean
assert check(ROOT) == [], check(ROOT)
print('data sources gate: OK')
