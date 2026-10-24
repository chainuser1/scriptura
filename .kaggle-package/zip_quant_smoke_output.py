"""Paste into a new Kaggle notebook cell and run once, after gte/ettin150/ettin400 have all finished in
/kaggle/working/quant-smoke/ (per the quantization smoke-check script). Zips the three *.json reports plus
the onnx-export/ ONNX model files into one archive and prints a clickable download link right in the cell's
own output -- the Output pane can be unreliable for a fresh file in the same session, so this does not
depend on it. Leaves the original files untouched so you can keep re-running models afterward if needed.

Set INCLUDE_ONNX_MODELS = False below to skip the (potentially large) exported .onnx model files and zip
only the JSON reports -- usually all you actually need to see the pass/fail numbers.
"""
import shutil
from pathlib import Path
from IPython.display import FileLink, display

INCLUDE_ONNX_MODELS = True  # set False to zip only the *.json reports, skipping the larger .onnx files

OUT = Path('/kaggle/working')
SRC = OUT / 'quant-smoke'
STAGE = OUT / 'quant-smoke-results'
STAGE.mkdir(exist_ok=True)

for name in ('gte', 'ettin150', 'ettin400'):
    report = SRC / f'{name}.json'
    if report.exists():
        shutil.copy2(report, STAGE / f'{name}.json')
        print(f'staged {name}.json')
    else:
        print(f'skipped {name}.json (not found -- did it finish running?)')

if INCLUDE_ONNX_MODELS:
    onnx_src = SRC / 'onnx-export'
    if onnx_src.exists():
        shutil.copytree(onnx_src, STAGE / 'onnx-export', dirs_exist_ok=True)
        print('staged onnx-export/')
    else:
        print('skipped onnx-export/ (not found)')

zip_path = Path(shutil.make_archive(str(OUT / 'quant-smoke-results'), 'zip', root_dir=STAGE))
print(f'wrote {zip_path} ({zip_path.stat().st_size / 1e6:.1f} MB)')
display(FileLink(str(zip_path.relative_to(OUT))))  # clickable link in the cell output, below this print
