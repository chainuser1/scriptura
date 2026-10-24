"""Paste into a new Kaggle notebook cell and run once, after gte/ettin150/ettin400 have all finished in
/kaggle/working/quant-smoke/ (per the quantization smoke-check script). Zips each model's report + exported
ONNX files into its OWN zip (gte.zip, ettin150.zip, ettin400.zip), then wraps all three individual zips into
one outer zip -- so you can grab a single model's results without unpacking everything else. Prints a
clickable download link for the outer zip right in the cell's own output -- the Output pane can be
unreliable for a fresh file in the same session, so this does not depend on it. Leaves the original
quant-smoke/ model outputs untouched so you can keep re-running models afterward if needed; only this
script's own staging folder and previously-written zip are cleared and rebuilt fresh each run.

Set INCLUDE_ONNX_MODELS = False below to skip the (potentially large) exported .onnx model files and zip
only each model's JSON report -- usually all you actually need to see the pass/fail numbers.
"""
import shutil
from pathlib import Path
from IPython.display import FileLink, display

INCLUDE_ONNX_MODELS = True  # set False to zip only the *.json reports, skipping the larger .onnx files

OUT = Path('/kaggle/working')
SRC = OUT / 'quant-smoke'
STAGE = OUT / 'quant-smoke-results'

# Clean slate every run: a stale staging dir or leftover zip from a previous run could otherwise mix old
# and new files together, or make shutil.make_archive fail outright on a pre-existing output path.
if STAGE.exists():
    shutil.rmtree(STAGE)
STAGE.mkdir()
outer_zip_path = OUT / 'quant-smoke-results.zip'
if outer_zip_path.exists():
    outer_zip_path.unlink()

individual_zips = []
for name in ('gte', 'ettin150', 'ettin400'):
    report = SRC / f'{name}.json'
    if not report.exists():
        print(f'skipped {name} (not found -- did it finish running?)')
        continue
    model_stage = STAGE / name
    model_stage.mkdir(exist_ok=True)
    shutil.copy2(report, model_stage / f'{name}.json')
    if INCLUDE_ONNX_MODELS:
        onnx_src = SRC / 'onnx-export' / name
        if onnx_src.exists():
            shutil.copytree(onnx_src, model_stage / 'onnx-export', dirs_exist_ok=True)
    model_zip = Path(shutil.make_archive(str(STAGE / name), 'zip', root_dir=model_stage))
    individual_zips.append(model_zip)
    print(f'wrote {model_zip} ({model_zip.stat().st_size / 1e6:.1f} MB)')

outer_stage = STAGE / '_outer'
outer_stage.mkdir(exist_ok=True)
for z in individual_zips:
    shutil.copy2(z, outer_stage / z.name)
outer_zip = Path(shutil.make_archive(str(OUT / 'quant-smoke-results'), 'zip', root_dir=outer_stage))
print(f'wrote {outer_zip} ({outer_zip.stat().st_size / 1e6:.1f} MB) containing {len(individual_zips)} model zip(s)')
display(FileLink(str(outer_zip.relative_to(OUT))))  # clickable link in the cell output, below this print
