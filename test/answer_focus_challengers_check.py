"""Run with .venv/Scripts/python.exe -I test/answer_focus_challengers_check.py."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'tool'))
import answer_focus_challengers as run

assert run.order([2., 4., 4., -1.]) == [1, 2, 0, 3]
for invalid in ([float('nan')], [float('inf')], [None], []):
    try:
        run.order(invalid)
    except AssertionError:
        pass
    else:
        raise AssertionError('Invalid ranking accepted')
with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp)/'identity.json'
    run.frozen(path, {'hash': 'original'})
    run.frozen(path, {'hash': 'original'})
    try:
        run.frozen(path, {'hash': 'changed'})
    except AssertionError:
        pass
    else:
        raise AssertionError('Changed input silently accepted')
assert len(run.source_rows()) == 10
assert 'scripture' not in run.INSTRUCTION.lower()
print('Challenger checks passed: stable ordering, invalid-score rejection, immutable identity, complete cached pools.')
