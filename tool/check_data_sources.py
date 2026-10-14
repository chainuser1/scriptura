"""Fail if app code or pubspec can reach a legacy data source.

  .venv\\Scripts\\python.exe -I tool/check_data_sources.py
"""
import re
import sys
from pathlib import Path

FORBIDDEN = [
    r'assets/resources', r'legacy-quarantine',
    r'verse-embeddings\.db', r'verse_embeddings\.db', r'verse-graph\.db', r'search-graph\.db',
    r'concept-embeddings\.db', r'user-data\.db', r'model_quantized\.onnx',
    r'github\.com/chainuser1/scicp', r'releases/download',
    r'package:sqflite', r'package:dio',
]
PATTERN = re.compile('|'.join(FORBIDDEN))


def check(root):
    root = Path(root)
    out = []
    files = list((root / 'lib').rglob('*.dart')) if (root / 'lib').exists() else []
    if (root / 'pubspec.yaml').exists():
        files.append(root / 'pubspec.yaml')
    for f in files:
        for n, line in enumerate(f.read_text('utf-8', errors='replace').splitlines(), 1):
            m = PATTERN.search(line)
            if m:
                out.append(f'{f.relative_to(root).as_posix()}:{n}: references "{m.group(0)}"')
    if (root / 'assets' / 'resources').exists():
        out.append('assets/resources still exists (move it to legacy-quarantine, Task 2)')
    return out


if __name__ == '__main__':
    problems = check(Path(__file__).resolve().parent.parent)
    print('\n'.join(problems) if problems else 'data sources: clean')
    sys.exit(1 if problems else 0)
