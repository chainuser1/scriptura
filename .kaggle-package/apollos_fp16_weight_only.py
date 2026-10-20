"""Standalone Kaggle cell: FP16 weight storage with FP32 calculations.

Reuses the verified prepared FP32 export. Converts only eligible constant
2-D MatMul weights to FP16, inserting Cast(to=FLOAT) before MatMul. Other
weights and activations remain unchanged. Each heavy step runs separately.
All saved test pairs must pass absolute error <= 0.05 before packaging.
This is not a retrieval benchmark or a guarantee of lower runtime RAM.
"""
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path('/kaggle/working')
OUT = ROOT / 'apollos-export-dynamic-v2'
PREPARED = OUT / 'int8-prepared/model.onnx'
REFERENCES = OUT / 'fp32/references.json'
TOKENIZER = OUT / 'tokenizer'
PACK = ROOT / 'apollos-fp16-weight-only-v1'
MODEL_PATH = PACK / 'model.onnx'
MODEL = 'nvidia/llama-nemotron-rerank-1b-v2'
REVISION = '828765652b05bd439c9789d2a6d093db1caa1443'
SETTINGS = {'method': 'weight_only_cast_matmul', 'weight_type': 'float16',
            'activation_type': 'float32', 'scope': 'constant_2d_matmul_weights'}

# The notebook process stays small; children do the heavy work.
CHILD_ENV = dict(os.environ, USE_TORCH='0', USE_TF='0',
                 OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2',
                 TOKENIZERS_PARALLELISM='false', MALLOC_ARENA_MAX='2')


def run_step(label, code, *arguments):
    print(f'\n{label}', flush=True)
    result = subprocess.run(
        [sys.executable, '-u', '-c', code, *map(str, arguments)],
        env=CHILD_ENV,
    )
    if result.returncode:
        hint = (' The worker was killed; check Kaggle RAM usage.'
                if result.returncode == -9 else '')
        raise RuntimeError(f'{label} failed (exit {result.returncode}).{hint} '
                           'No new verified ZIP was created.')


VERIFY = r'''
import json, sys
from pathlib import Path
import numpy as np
import onnxruntime as ort
from transformers import AutoTokenizer

model_path, tokenizer_path, references_path, tolerance, report_path = sys.argv[1:]
tolerance = float(tolerance)
references = json.loads(Path(references_path).read_text())
if not references:
    raise RuntimeError('No saved reference cases found')
tokenizer = AutoTokenizer.from_pretrained(tokenizer_path, local_files_only=True)
options = ort.SessionOptions()
options.intra_op_num_threads = 2
options.inter_op_num_threads = 1
options.enable_cpu_mem_arena = False
options.enable_mem_pattern = False
# Reduce session initialization memory. Record this validation setting.
options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
options.add_session_config_entry('session.disable_prepacking', '1')
session = ort.InferenceSession(model_path, sess_options=options,
                               providers=['CPUExecutionProvider'])
results = []
failures = []
for case in references:
    text = f"question:{case['query']} \n \n passage:{case['passage']}"
    enc = tokenizer(text, return_tensors='np', truncation=True, max_length=8192)
    tokens = int(enc['input_ids'].shape[1])
    if tokens != case['tokens']:
        raise RuntimeError('Token count changed from the original reference')
    feed = {name: enc[name].astype(np.int64)
            for name in ('input_ids', 'attention_mask')}
    score = float(session.run(['logits'], feed)[0].reshape(-1)[0])
    difference = abs(score - case['logit'])
    print(f'tokens={tokens}, score={score:.6f}, '
          f"reference={case['logit']:.6f}, difference={difference:.6f}", flush=True)
    if not np.isfinite(score) or difference > tolerance:
        failures.append({'tokens': tokens, 'difference': difference})
    results.append({**case, 'onnx_logit': score, 'difference': difference})
report = {'status': 'failed' if failures else 'passed', 'provider': 'CPUExecutionProvider',
          'graph_optimizations': 'disabled', 'prepacking': 'disabled',
          'absolute_tolerance': tolerance, 'cases': results,
          'scope': 'Conversion smoke tests; not a retrieval-quality benchmark'}
Path(report_path).write_text(json.dumps(report, indent=2) + '\n')
if failures:
    raise RuntimeError(f'{len(failures)} case(s) failed the unchanged tolerance '
                       f'{tolerance}. All scores are printed above. Packaging stopped.')
'''

QUANTIZE = r'''
import gc, sys
from pathlib import Path
import numpy as np
import onnx
from onnx import numpy_helper, helper
from onnxruntime.quantization.onnx_model import ONNXModel

source, destination = sys.argv[1:]
model = onnx.load(source)
weights = {t.name: t for t in model.graph.initializer}
occupied = set(weights)
for node in model.graph.node:
    occupied.update(node.input)
    occupied.update(node.output)
new_nodes = []
converted = {}
for node in model.graph.node:
    if node.domain not in ('', 'ai.onnx') or node.op_type != 'MatMul':
        new_nodes.append(node)
        continue
    name = node.input[1]
    tensor = weights.get(name)
    if tensor is None or tensor.data_type != onnx.TensorProto.FLOAT or len(tensor.dims) != 2:
        new_nodes.append(node)
        continue
    if name not in converted:
        count = len(converted) + 1
        prefix = f'apollos_fp16_weight_only_{count}_'
        halfname, floatname = prefix + 'half', prefix + 'float'
        if halfname in occupied or floatname in occupied:
            raise RuntimeError('Generated tensor name collides with an existing name')
        occupied.update((halfname, floatname))
        values = numpy_helper.to_array(tensor)
        if not np.all(np.isfinite(values)):
            raise RuntimeError(f'Non-finite source weights: {name}')
        with np.errstate(over='ignore', invalid='ignore'):
            half = values.astype(np.float16)
        if not np.all(np.isfinite(half)):
            raise RuntimeError(f'FP16 overflow in {name}; conversion stopped without clipping')
        model.graph.initializer.append(numpy_helper.from_array(half, name=halfname))
        new_nodes.append(helper.make_node(
            'Cast', [halfname], [floatname], to=onnx.TensorProto.FLOAT,
            name=prefix + 'cast_to_fp32'))
        converted[name] = floatname
        print(f'FP16 weight matrix {count}: {name} {list(tensor.dims)}', flush=True)
        del values, half
    copied = onnx.NodeProto()
    copied.CopyFrom(node)
    copied.input[1] = converted[name]
    new_nodes.append(copied)
if not converted:
    raise RuntimeError('No eligible constant FP32 MatMul weights found')
del model.graph.node[:]
model.graph.node.extend(new_nodes)
# Retain an original FP32 weight if another operation still needs it.
wrapped = ONNXModel(model)
wrapped.clean_initializers()
del weights, new_nodes, wrapped
gc.collect()
onnx.save_model(model, destination, save_as_external_data=True,
                all_tensors_to_one_file=True, location='model.onnx.data',
                size_threshold=1024)
del model
gc.collect()
onnx.checker.check_model(destination)
Path(destination).with_name('converted.ok').write_text('converted\n')
print('FP16 weight-only conversion finished; numerical verification is next.', flush=True)
'''


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    for path in (PREPARED, REFERENCES, TOKENIZER / 'tokenizer.json'):
        if not path.is_file():
            raise FileNotFoundError(f'Required saved file is missing: {path}')

    needed = {'onnx': 'onnx', 'onnxruntime': 'onnxruntime',
              'transformers': 'transformers', 'huggingface_hub': 'huggingface_hub'}
    missing = [package for module, package in needed.items()
               if importlib.util.find_spec(module) is None]
    if missing:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', *missing])

    print(f'Free disk: {shutil.disk_usage(ROOT).free / 1024**3:.2f} GiB', flush=True)
    run_step('Checking saved prepared FP32...', VERIFY,
             PREPARED, TOKENIZER, REFERENCES, 0.01,
             OUT / 'prepared-verification-resume.json')

    # Use a distinct settings marker; never mistake older output for this retry.
    marker = PACK / 'resume-settings.json'
    reusable = (MODEL_PATH.is_file() and (PACK / 'converted.ok').is_file()
                and marker.is_file() and json.loads(marker.read_text()) == SETTINGS)
    if not reusable:
        # Only discard this retry's incomplete output, never source models.
        if PACK.exists():
            shutil.rmtree(PACK)
        PACK.mkdir()
        marker.write_text(json.dumps(SETTINGS, indent=2) + '\n')
        run_step('Building FP16 in a separate process...', QUANTIZE,
                 PREPARED, MODEL_PATH)
    else:
        print('Reusing this retry\'s completed conversion; rechecking scores.', flush=True)

    run_step('Checking FP16 against original reference scores...', VERIFY,
             MODEL_PATH, TOKENIZER, REFERENCES, 0.05, PACK / 'verification.json')
    report_path = PACK / 'verification.json'
    report = json.loads(report_path.read_text())
    report['quantization'] = SETTINGS
    report_path.write_text(json.dumps(report, indent=2) + '\n')

    # No second copy of the model directory is needed for packaging.
    from huggingface_hub import hf_hub_download
    for filename, destination in [('LICENSE', 'LICENSE'), ('README.md', 'UPSTREAM_README.md')]:
        upstream = hf_hub_download(MODEL, filename, revision=REVISION)
        shutil.copy2(upstream, PACK / destination)
    for asset in TOKENIZER.iterdir():
        if asset.is_file():
            shutil.copy2(asset, PACK / asset.name)
    # Retain conversion/settings markers; numerical checks run on every retry.
    (PACK / 'CONVERSION_NOTICE.txt').write_text(
        f'Apollos uses {MODEL} by NVIDIA.\nRevision: {REVISION}\n'
        'Converted to ONNX by Scriptura Labs. No fine-tuning was performed.\n'
        'Eligible constant 2-D MatMul weights are stored in FP16 and cast to\n'
        'FP32 before multiplication. Other weights and activations are unchanged.\n'
        'Smaller weight storage does not guarantee lower runtime RAM or faster\n'
        'inference. See LICENSE and UPSTREAM_README.md.\n')
    # Exclude the manifest from its own checksums, including on a resumed run.
    files = {p.name: {'bytes': p.stat().st_size, 'sha256': digest(p)}
             for p in sorted(PACK.iterdir()) if p.is_file() and p.name != 'manifest.json'}
    (PACK / 'manifest.json').write_text(json.dumps({
        'format': 'apollos-fp16-v1', 'model': MODEL, 'revision': REVISION,
        'weights': 'fp16', 'quantization': SETTINGS, 'batch_size': 1,
        'min_sequence_length': 2, 'max_sequence_length': 8192, 'files': files,
    }, indent=2) + '\n')

    archive = ROOT / 'apollos-fp16-weight-only-v1.zip'
    temporary = ROOT / 'apollos-fp16-weight-only-v1.zip.partial'
    temporary.unlink(missing_ok=True)
    required = sum(p.stat().st_size for p in PACK.iterdir() if p.is_file())
    if shutil.disk_usage(ROOT).free < required + 64 * 1024**2:
        raise RuntimeError('FP16 passed, but there is not enough space for its ZIP. '
                           'The verified model folder is preserved.')
    print('\nWriting ZIP without duplicating the model folder...', flush=True)
    with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_STORED,
                         allowZip64=True) as bundle:
        for file in sorted(PACK.iterdir()):
            if file.is_file():
                bundle.write(file, arcname=f'{PACK.name}/{file.name}')
    temporary.replace(archive)
    print(f'READY: {archive} ({archive.stat().st_size / 1024**3:.2f} GiB)', flush=True)
    try:
        from IPython.display import FileLink, display
        os.chdir(ROOT)
        display(FileLink(archive.name))
    except ImportError:
        pass


if __name__ == '__main__':
    main()
