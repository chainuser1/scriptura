"""Paste into a new Kaggle notebook cell and run once, after gte/ettin150/ettin400 have all finished (per
answer_focus_challengers_round2_kaggle.py). Zips /kaggle/working/gte, /ettin150, /ettin400 into one file and
prints a clickable download link right in the cell's own output -- the Output pane can be unreliable for a
fresh file in the same session, so this does not depend on it. Leaves the original folders untouched so you
can keep re-running models afterward if needed.
"""
import shutil
from pathlib import Path
from IPython.display import FileLink, display

OUT = Path('/kaggle/working')
STAGE = OUT / 'round2-results'
STAGE.mkdir(exist_ok=True)

for name in ('gte', 'ettin150', 'ettin400'):
    src = OUT / name
    if src.exists():
        shutil.copytree(src, STAGE / name, dirs_exist_ok=True)
        print(f'staged {name}')
    else:
        print(f'skipped {name} (not found -- did it finish running?)')

zip_path = Path(shutil.make_archive(str(OUT / 'round2-results'), 'zip', root_dir=STAGE))
print(f'wrote {zip_path} ({zip_path.stat().st_size / 1e6:.1f} MB)')
display(FileLink(str(zip_path.relative_to(OUT))))  # clickable link in the cell output, below this print
