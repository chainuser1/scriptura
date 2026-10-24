"""Paste into a new Kaggle notebook cell and run once, after gte/ettin150/ettin400 have all finished in
/kaggle/working/quant-smoke/ (per the quantization smoke-check script). Zips each model's report + exported
ONNX files into its OWN zip (gte.zip, ettin150.zip, ettin400.zip), then wraps all three individual zips into
one outer zip -- so you can grab a single model's results without unpacking everything else. Prints a
clickable download link for the outer zip right in the cell's own output -- the Output pane can be
unreliable for a fresh file in the same session, so this does not depend on it. Leaves the original
quant-smoke/ model outputs untouched -- only this script's own output files are created/cleared.

Storage-conscious by design (Kaggle's /kaggle/working quota is limited, and the exported ONNX files can be
several GB per model): zips straight from the source files with zipfile (no shutil.copytree staging copy
first), and deletes each per-model zip right after it is folded into the outer zip -- so at most one extra
full copy of the data exists on disk at a time (the zip currently being written), not the ~3-4x a naive
copy-then-zip-then-copy-again chain would otherwise leave sitting around simultaneously.

Set INCLUDE_ONNX_MODELS = False below to skip the (potentially large) exported .onnx model files and zip
only each model's JSON report -- usually all you actually need to see the pass/fail numbers, and the
cheapest option storage-wise since there is then nothing large to zip at all.
"""
import zipfile
from pathlib import Path
from IPython.display import FileLink, display

INCLUDE_ONNX_MODELS = True  # set False to zip only the *.json reports, skipping the larger .onnx files

OUT = Path('/kaggle/working')
SRC = OUT / 'quant-smoke'
OUTER_ZIP = OUT / 'quant-smoke-results.zip'

# Clean slate every run: a leftover zip from a previous run could otherwise make zipfile append to stale
# data, or just waste space sitting alongside the new one.
if OUTER_ZIP.exists():
    OUTER_ZIP.unlink()

individual_zip_paths = []
for name in ('gte', 'ettin150', 'ettin400'):
    report = SRC / f'{name}.json'
    if not report.exists():
        print(f'skipped {name} (not found -- did it finish running?)')
        continue
    model_zip_path = OUT / f'{name}.zip'
    if model_zip_path.exists():
        model_zip_path.unlink()
    with zipfile.ZipFile(model_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(report, arcname=f'{name}.json')
        if INCLUDE_ONNX_MODELS:
            onnx_src = SRC / 'onnx-export' / name
            if onnx_src.exists():
                for f in onnx_src.rglob('*'):
                    if f.is_file():
                        zf.write(f, arcname=f'onnx-export/{f.relative_to(onnx_src)}')
    individual_zip_paths.append(model_zip_path)
    print(f'wrote {model_zip_path} ({model_zip_path.stat().st_size / 1e6:.1f} MB)')

with zipfile.ZipFile(OUTER_ZIP, 'w', zipfile.ZIP_STORED) as outer:  # STORED: contents are already compressed
    for z in individual_zip_paths:
        outer.write(z, arcname=z.name)
        z.unlink()  # free the per-model zip's space immediately now that it's folded into the outer zip

print(f'wrote {OUTER_ZIP} ({OUTER_ZIP.stat().st_size / 1e6:.1f} MB) containing {len(individual_zip_paths)} model zip(s)')
display(FileLink(str(OUTER_ZIP.relative_to(OUT))))  # clickable link in the cell output, below this print
