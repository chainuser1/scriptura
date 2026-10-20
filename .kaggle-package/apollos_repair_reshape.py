"""Graph-only repair for the inspected Apollos FP16 weight-only pack.

Paste into a NEW Kaggle cell, or run with Python on an extracted pack.
Requires the existing model.onnx.data and tokenizer files beside model.onnx.
No weight conversion or full-size copy is performed. DirectML is NOT tested.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

KNOWN_SOURCE = '2d061742f9d6d1ee6ff69cac7fa2d95f4f78b454559684080f45db838d41dd5d'
KNOWN_FIXED = '572b999efba388b042950a0e767b1765981f48613b26d33e631fa5fae962fa36'
EXPECTED_COUNT = 96
CPU_TOLERANCE = 0.05
REPAIR_TOLERANCE = 0.0001


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def patch_graph(model):
    """Only patch constant, integer, zero-free shape vectors. No guesses."""
    import onnx
    import numpy as np
    initializers = {tensor.name: tensor for tensor in model.graph.initializer}
    changes = []
    for index, node in enumerate(model.graph.node):
        if node.domain not in ('', 'ai.onnx') or node.op_type != 'Reshape':
            continue
        attribute = next((a for a in node.attribute if a.name == 'allowzero' and a.i == 1), None)
        if attribute is None:
            continue
        tensor = initializers.get(node.input[1])
        if tensor is None or tensor.external_data:
            raise RuntimeError(f'{node.name}: target shape is not an inline constant. No repair committed.')
        values = onnx.numpy_helper.to_array(tensor)
        if values.ndim != 1 or not np.issubdtype(values.dtype, np.integer):
            raise RuntimeError(f'{node.name}: target shape is not an integer vector.')
        shape = [int(v) for v in values]
        if 0 in shape or any(v < -1 for v in shape) or shape.count(-1) > 1:
            raise RuntimeError(f'{node.name}: cannot safely change allowzero for {shape}.')
        changes.append({'node_index': index, 'name': node.name,
                        'shape_tensor': node.input[1], 'target_shape': shape})
        attribute.i = 0
    return changes


VERIFY = r'''
import json, sys
from pathlib import Path
import numpy as np
import onnxruntime as ort
from transformers import AutoTokenizer

pack, candidate, report_path, cpu_tolerance, repair_tolerance = sys.argv[1:]
pack = Path(pack)
cpu_tolerance, repair_tolerance = float(cpu_tolerance), float(repair_tolerance)
previous = json.loads((pack / 'verification.json').read_text())
cases = previous['cases']
if len(cases) != 3 or previous.get('status') != 'passed':
    raise RuntimeError('Expected a passing original report with exactly three cases.')
tokenizer = AutoTokenizer.from_pretrained(pack, local_files_only=True)
options = ort.SessionOptions()
options.intra_op_num_threads = 2
options.inter_op_num_threads = 1
options.enable_cpu_mem_arena = False
options.enable_mem_pattern = False
options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
options.add_session_config_entry('session.disable_prepacking', '1')
session = ort.InferenceSession(candidate, sess_options=options,
                               providers=['CPUExecutionProvider'])
results, failures = [], []
for case in cases:
    text = f"question:{case['query']} \n \n passage:{case['passage']}"
    encoded = tokenizer(text, return_tensors='np', truncation=True, max_length=8192)
    if encoded['input_ids'].shape[1] != case['tokens']:
        raise RuntimeError('Token count differs from original verification.')
    feed = {k: encoded[k].astype(np.int64) for k in ('input_ids', 'attention_mask')}
    score = float(session.run(['logits'], feed)[0].reshape(-1)[0])
    difference = abs(score - case['logit'])
    repair_difference = abs(score - case['onnx_logit'])
    passed = (np.isfinite(score) and difference <= cpu_tolerance
              and repair_difference <= repair_tolerance)
    print(f"tokens={case['tokens']}, score={score:.9f}, "
          f'FP32 difference={difference:.9f}, repair difference={repair_difference:.9f}, '
          f"{'PASS' if passed else 'FAIL'}", flush=True)
    if not passed:
        failures.append(case['tokens'])
    results.append({**case, 'pre_repair_onnx_logit': case['onnx_logit'],
                    'onnx_logit': score, 'difference': difference,
                    'repair_difference': repair_difference})
report = {**previous, 'status': 'failed' if failures else 'passed',
          'absolute_tolerance': cpu_tolerance,
          'repair_absolute_tolerance': repair_tolerance, 'cases': results,
          'provider': 'CPUExecutionProvider', 'graph_optimizations': 'disabled',
          'prepacking': 'disabled',
          'directml': {'status': 'not_run',
                       'required_next_check': 'Run this repaired pack on Windows DirectML; inspect GPU placement and scores.'}}
Path(report_path).write_text(json.dumps(report, indent=2) + '\n')
if failures:
    raise RuntimeError('Numerical checks failed. The original graph is unchanged.')
'''


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    default = '/kaggle/working/apollos-fp16-weight-only-v1'
    parser.add_argument('--pack', type=Path, default=Path(default), help='Existing extracted FP16 weight-only folder')
    args = parser.parse_args(argv)
    pack = args.pack.resolve()
    required = ('model.onnx', 'model.onnx.data', 'tokenizer.json', 'verification.json', 'manifest.json')
    for name in required:
        if not (pack / name).is_file():
            raise FileNotFoundError(f'Missing {pack / name}. Use the existing extracted pack, including its weights.')

    packages = {'onnx': 'onnx', 'onnxruntime': 'onnxruntime', 'transformers': 'transformers'}
    missing = [package for module, package in packages.items() if importlib.util.find_spec(module) is None]
    if missing:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', *missing])
    import onnx

    original = pack / 'model.onnx'
    source_hash = sha256(original)
    if source_hash not in (KNOWN_SOURCE, KNOWN_FIXED):
        raise RuntimeError('This graph differs from the inspected graph. No files changed; send its model.onnx for review.')
    model = onnx.load(original, load_external_data=False)
    changes = patch_graph(model)
    expected = EXPECTED_COUNT if source_hash == KNOWN_SOURCE else 0
    if len(changes) != expected:
        raise RuntimeError(f'Expected {expected} changes, found {len(changes)}. No repair committed.')
    fixed_bytes = model.SerializeToString()
    fixed_hash = hashlib.sha256(fixed_bytes).hexdigest()
    if fixed_hash != KNOWN_FIXED:
        raise RuntimeError('Patched graph does not match the audited graph. No repair committed.')
    print(f'Confirmed {len(changes)} safe changes. All target shapes are constant and contain no zeros.', flush=True)

    candidate = pack / 'model.reshape-candidate.onnx'
    candidate.write_bytes(fixed_bytes)
    # Full file-path validation is possible here because weights are present.
    onnx.checker.check_model(str(candidate))
    report_path = pack / 'reshape-verification.pending.json'
    env = dict(os.environ, USE_TORCH='0', USE_TF='0', OMP_NUM_THREADS='2',
               OPENBLAS_NUM_THREADS='2', TOKENIZERS_PARALLELISM='false')
    print('Checking all three pairs on CPU before committing the repair...', flush=True)
    result = subprocess.run([sys.executable, '-u', '-c', VERIFY, str(pack), str(candidate),
                             str(report_path), str(CPU_TOLERANCE), str(REPAIR_TOLERANCE)], env=env)
    if result.returncode:
        raise RuntimeError('Verification failed or worker stopped. Original model.onnx was NOT replaced.')

    # Back up small graph/metadata files outside the pack. Never copy weights.
    backup = pack.parent / (pack.name + '-before-reshape')
    backup.mkdir(exist_ok=True)
    for name in ('model.onnx', 'manifest.json', 'verification.json', 'CONVERSION_NOTICE.txt'):
        source, saved = pack / name, backup / name
        if source.is_file() and not saved.exists():
            shutil.copy2(source, saved)
    candidate.replace(original)
    report_path.replace(pack / 'verification.json')
    repair = {'status': 'graph_repaired_cpu_verified', 'source_sha256': source_hash,
              'patched_sha256': fixed_hash, 'changed_nodes_this_run': len(changes),
              'audited_original_allowzero_one_count': EXPECTED_COUNT,
              'remaining_allowzero_one_count': 0,
              'proof': 'All affected target shapes are constant integer vectors without zero entries. Changing allowzero cannot change their reshape behavior.',
              'changes': changes, 'weights_changed': False,
              'directml_status': 'not_run_windows_test_required'}
    earlier_repair = pack / 'reshape-repair.json'
    if not changes and earlier_repair.is_file():
        recorded = json.loads(earlier_repair.read_text())
        if recorded.get('patched_sha256') == fixed_hash:
            repair = recorded  # Retain the original 96-node provenance on rerun.
    write_json(pack / 'reshape-repair.json', repair)
    notice = pack / 'CONVERSION_NOTICE.txt'
    message = ('\nReshape compatibility repair: audited zero-free constant target shapes; '
               'allowzero set to 0. Weight bytes unchanged. CPU checks passed at 0.05; '
               'DirectML execution is not yet verified.\n')
    existing = notice.read_text(encoding='utf-8') if notice.exists() else ''
    if message.strip() not in existing:
        notice.write_text(existing + message, encoding='utf-8')
    manifest = json.loads((pack / 'manifest.json').read_text())
    manifest['graph_repair'] = {k: v for k, v in repair.items() if k != 'changes'}
    manifest['files'] = {p.relative_to(pack).as_posix(): {'bytes': p.stat().st_size, 'sha256': sha256(p)}
                         for p in sorted(pack.rglob('*')) if p.is_file() and p != pack / 'manifest.json'}
    write_json(pack / 'manifest.json', manifest)
    print('Graph and checksums updated. Large weight files were not rewritten.', flush=True)

    archive = pack.parent / (pack.name + '-reshape-v2.zip')
    partial = archive.with_suffix('.zip.partial')
    partial.unlink(missing_ok=True)
    payload = sum(p.stat().st_size for p in pack.rglob('*') if p.is_file())
    free = shutil.disk_usage(pack).free
    if free < payload + 64 * 1024**2:
        raise RuntimeError(f'Repair and CPU verification succeeded. ZIP needs about {payload / 1024**3:.2f} GiB; '
                           f'only {free / 1024**3:.2f} GiB is free. The repaired folder is preserved. '
                           'Free space and rerun this same script.')
    print('Writing repaired ZIP...', flush=True)
    with zipfile.ZipFile(partial, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as bundle:
        for p in sorted(pack.rglob('*')):
            if p.is_file():
                bundle.write(p, arcname=p.relative_to(pack.parent).as_posix())
    partial.replace(archive)
    print(f'READY: {archive}\nCPU verified. DirectML remains NOT VERIFIED.', flush=True)
    try:
        from IPython.display import FileLink, display
        os.chdir(archive.parent)
        display(FileLink(archive.name))
    except ImportError:
        pass


if __name__ == '__main__':
    main([] if 'ipykernel' in sys.modules else None)
