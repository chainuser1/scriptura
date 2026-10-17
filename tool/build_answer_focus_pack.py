"""Build the two Answer focus packs (BAAI/bge-reranker-v2-m3 as ONNX) into generated-artifacts/:

  answer-focus-int8-v1/  model.onnx (int8 weights, for the CPU), tokenizer.json, LICENSE, manifest.json
  answer-focus-fp16-v1/  model.onnx (fp16 weights, for the graphics chip), tokenizer.json, LICENSE, manifest.json

Each model is one file (no external data). tool/make_bucket_index.py zips and lists them as optional packs.

  .venv\\Scripts\\python.exe -I tool/build_answer_focus_pack.py
"""
import hashlib
import json
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
from reranker_speed import MODEL, OUT, export  # noqa: E402

APACHE = 'https://www.apache.org/licenses/LICENSE-2.0.txt'
NOTICE = ('Answer focus uses BAAI/bge-reranker-v2-m3 (https://huggingface.co/BAAI/bge-reranker-v2-m3) by the Beijing Academy '
          'of Artificial Intelligence, licensed under the Apache License 2.0 (below). Converted to ONNX; weights quantized '
          'to {kind} by Scriptura Labs. No other changes.\n\n')


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 22), b''):
            h.update(c)
    return h.hexdigest()


def fp16_path():
    from reranker_gpu import fp16_model
    return fp16_model()


def build(pid, source, kind, licence):
    import onnx
    from huggingface_hub import hf_hub_download
    dst = ROOT / 'generated-artifacts' / pid
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    onnx.save(onnx.load(str(source)), str(dst / 'model.onnx'))  # loads external data, saves one file
    shutil.copy(hf_hub_download(MODEL, 'tokenizer.json'), dst / 'tokenizer.json')
    (dst / 'LICENSE').write_text(NOTICE.format(kind=kind) + licence, 'utf-8')
    files = {n: {'bytes': (dst / n).stat().st_size, 'sha256': sha256(dst / n)} for n in ('model.onnx', 'tokenizer.json', 'LICENSE')}
    (dst / 'manifest.json').write_text(json.dumps({'format': pid, 'model': MODEL, 'weights': kind, 'files': files}, indent=1), 'utf-8')
    print(f'{pid}: {files["model.onnx"]["bytes"] / 2**20:.0f} MB')


def main():
    _, int8 = export()
    licence = urllib.request.urlopen(APACHE, timeout=30).read().decode('utf-8')
    build('answer-focus-int8-v1', int8, 'int8', licence)
    build('answer-focus-fp16-v1', fp16_path(), 'fp16', licence)


if __name__ == '__main__':
    main()
