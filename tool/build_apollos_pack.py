"""Build the Apollos (nvidia/llama-nemotron-rerank-1b-v2) Answer focus packs into generated-artifacts/:

  apollos-int8-v1/  model.onnx (+ model.onnx.data), tokenizer.json, LICENSE, manifest.json (int8, CPU)
  apollos-fp16-v1/  model.onnx (+ model.onnx.data), tokenizer.json, LICENSE, manifest.json (fp16, graphics chip)

Unlike Ezra (BGE-reranker-v2-m3), Apollos's legacy (TorchScript-tracer) ONNX export silently truncates
several large external-data weight tensors to 0 bytes without raising an error -- confirmed via a spike
(local-benchmarks/apollos-spike): onnxruntime only catches it at load time ("size to read: 67108864 given
file_length: 0"). The newer torch.export-based exporter (dynamo=True) does not have this bug and was
verified byte-for-byte correct against the PyTorch reference logit (17.411783 vs 17.41178321838379).
This script therefore uses dynamo=True, not Ezra's dynamo=False path.

The fp32 export is ~4.9 GB; disk space is handled carefully (checked before the heavy steps, the fp32
intermediate deleted immediately once both int8 and fp16 are derived from it -- never held alongside both
outputs at once).

  .venv\\Scripts\\python.exe -I tool/build_apollos_pack.py
"""
import hashlib
import json
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'local-benchmarks/apollos-export'
MODEL = 'nvidia/llama-nemotron-rerank-1b-v2'
REVISION = '828765652b05bd439c9789d2a6d093db1caa1443'
APACHE = 'https://www.apache.org/licenses/LICENSE-2.0.txt'
NOTICE = ('Apollos uses nvidia/llama-nemotron-rerank-1b-v2 (https://huggingface.co/nvidia/llama-nemotron-rerank-1b-v2) '
          'by NVIDIA, licensed under the Apache License 2.0 (below). Converted to ONNX; weights quantized to {kind} '
          'by Scriptura Labs. No other changes.\n\n')
MIN_FREE_GB = 8  # fp32 export (~4.9 GB) plus working headroom; checked before the export step


def free_gb():
    return shutil.disk_usage(ROOT.anchor).free / 2**30


def require_space(step):
    free = free_gb()
    assert free >= MIN_FREE_GB, f'{step}: only {free:.1f} GB free, need >= {MIN_FREE_GB} GB -- free up space first'
    print(f'{step}: {free:.1f} GB free', flush=True)


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 22), b''):
            h.update(c)
    return h.hexdigest()


def export_fp32():
    """ONNX fp32 export via the dynamo exporter (required for this model; see module docstring)."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    path = OUT / 'fp32/model.onnx'
    if path.exists():
        return path
    require_space('fp32 export')
    path.parent.mkdir(parents=True, exist_ok=True)
    tok = AutoTokenizer.from_pretrained(MODEL, revision=REVISION, trust_remote_code=True)
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL, revision=REVISION, trust_remote_code=True, dtype=torch.float32).eval()
    enc = tok('question:placeholder query \n \n passage:placeholder passage text', return_tensors='pt')
    torch.onnx.export(model, (enc['input_ids'], enc['attention_mask']), str(path),
                       input_names=['input_ids', 'attention_mask'], output_names=['logits'],
                       opset_version=18, dynamo=True)
    tok.save_pretrained(OUT / 'tokenizer')
    return path


def quantize_int8(fp32):
    path = OUT / 'int8/model.onnx'
    if path.exists():
        return path
    require_space('int8 quantization')
    from onnxruntime.quantization import QuantType, quantize_dynamic
    path.parent.mkdir(parents=True, exist_ok=True)
    quantize_dynamic(str(fp32), str(path), weight_type=QuantType.QInt8, use_external_data_format=True)
    return path


def convert_fp16(fp32):
    path = OUT / 'fp16/model.onnx'
    if path.exists():
        return path
    require_space('fp16 conversion')
    import onnx
    from onnxruntime.transformers.float16 import convert_float_to_float16
    path.parent.mkdir(parents=True, exist_ok=True)
    model = onnx.load(str(fp32))
    half = convert_float_to_float16(model, keep_io_types=True, disable_shape_infer=True)
    onnx.save(half, str(path))
    return path


def build(pid, source, kind, licence):
    import onnx
    dst = ROOT / 'generated-artifacts' / pid
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    onnx.save(onnx.load(str(source)), str(dst / 'model.onnx'))
    shutil.copy(OUT / 'tokenizer/tokenizer.json', dst / 'tokenizer.json')
    (dst / 'LICENSE').write_text(NOTICE.format(kind=kind) + licence, 'utf-8')
    files = {n.name: {'bytes': n.stat().st_size, 'sha256': sha256(n)} for n in dst.iterdir() if n.is_file()}
    (dst / 'manifest.json').write_text(json.dumps(
        {'format': pid, 'model': MODEL, 'revision': REVISION, 'weights': kind, 'files': files}, indent=1), 'utf-8')
    total_mb = sum(v['bytes'] for v in files.values()) / 2**20
    print(f'{pid}: {total_mb:.0f} MB', flush=True)


def main():
    fp32 = export_fp32()
    int8 = quantize_int8(fp32)
    fp16 = convert_fp16(fp32)
    if fp32.exists():
        fp32.unlink()
        for p in fp32.parent.glob('*.data'):
            p.unlink()
        print('fp32 intermediate deleted (int8 and fp16 both derived)', flush=True)

    licence = urllib.request.urlopen(APACHE, timeout=30).read().decode('utf-8')
    build('apollos-int8-v1', int8, 'int8', licence)
    build('apollos-fp16-v1', fp16, 'fp16', licence)


if __name__ == '__main__':
    main()
