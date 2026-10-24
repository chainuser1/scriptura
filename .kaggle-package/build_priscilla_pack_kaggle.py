"""Paste this entire script into ONE Kaggle Python notebook cell and run it.

Internet must be enabled. Uses CPU; requires enough RAM for the FP32 graph.
Exports dynamic-length ONNX, then builds an INT8 pack plus its ZIP.
Batch size is 1; supported sequence lengths are 2..512 tokens.
"""

import gc
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

MODEL = "Alibaba-NLP/gte-reranker-modernbert-base"
REVISION = "f7481e6055501a30fb19d090657df9ec1f79ab2c"
ROOT = Path("/kaggle/working") if Path("/kaggle/working").exists() else Path.cwd()
OUT = ROOT / "priscilla-export"
MAX_LENGTH = 512
THREADS = 4
TOLERANCES = {"fp32": 0.01, "int8": 0.05}
TEST_PAIRS = [
    ("What is the capital of France?", "Paris is the capital of France."),
    ("What is the capital of France?", "Bananas are a source of potassium."),
    ("How do plants make food?",
     "Plants use photosynthesis to convert sunlight, water, and carbon dioxide "
     "into sugars. Chlorophyll helps capture light energy in their leaves."),
]


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def encode(tokenizer, query, passage, tensors):
    return tokenizer(
        query, passage,
        return_tensors=tensors,
        truncation=True,
        max_length=MAX_LENGTH,
    )


def check_graph(path):
    import onnx
    # Use the file path, rather than a loaded protobuf, for large models.
    onnx.checker.check_model(str(path))
    graph = onnx.load(str(path), load_external_data=False)
    inputs = {item.name: item for item in graph.graph.input}
    for name in ("input_ids", "attention_mask"):
        dims = inputs[name].type.tensor_type.shape.dim
        if len(dims) != 2 or dims[0].dim_value != 1 or not dims[1].dim_param:
            raise RuntimeError(f"{path}: expected [1, dynamic_length] for {name}")


def stage(name):
    directory = OUT / name
    path = directory / "model.onnx"
    marker = directory / "complete.json"
    if path.is_file() and marker.is_file():
        check_graph(path)
        print(f"Reusing completed {name} export", flush=True)
        return path, True
    # A model file without its completion marker may be a partial write.
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)
    return path, False


def finish_stage(path):
    check_graph(path)
    save_json(path.parent / "complete.json", {"complete": True})
    gc.collect()


def export_fp32():
    import numpy as np
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    path, cached = stage("fp32")
    references_path = path.parent / "references.json"
    if cached:
        return path, json.loads(references_path.read_text(encoding="utf-8"))

    tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=REVISION)
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL, revision=REVISION, dtype=torch.float32,
    ).cpu().eval()

    class LogitsOnly(torch.nn.Module):
        def __init__(self, base):
            super().__init__()
            self.base = base

        def forward(self, input_ids, attention_mask):
            return self.base(
                input_ids=input_ids,
                attention_mask=attention_mask,
                return_dict=True,
            ).logits

    wrapper = LogitsOnly(model).eval()
    references = []
    print("Computing PyTorch FP32 reference scores...", flush=True)
    with torch.inference_mode():
        for query, passage in TEST_PAIRS:
            enc = encode(tokenizer, query, passage, "pt")
            logits = wrapper(enc["input_ids"], enc["attention_mask"])
            score = float(logits.reshape(-1)[0])
            if not np.isfinite(score):
                raise RuntimeError("PyTorch reference score is not finite")
            references.append({
                "query": query, "passage": passage, "logit": score,
                "tokens": int(enc["input_ids"].shape[1]),
            })

    enc = encode(tokenizer, "placeholder query", "placeholder passage text", "pt")
    sequence = torch.export.Dim("sequence_length", min=2, max=MAX_LENGTH)
    print("Exporting FP32 with Dynamo and dynamic sequence length...", flush=True)
    with torch.no_grad():
        program = torch.onnx.export(
            wrapper,
            (enc["input_ids"], enc["attention_mask"]),
            str(path),
            input_names=["input_ids", "attention_mask"],
            output_names=["logits"],
            opset_version=18,
            dynamo=True,
            external_data=True,
            dynamic_shapes=({1: sequence}, {1: sequence}),
        )
    tokenizer.save_pretrained(OUT / "tokenizer")
    save_json(references_path, references)
    del program, logits, enc, wrapper, model, tokenizer
    gc.collect()
    finish_stage(path)
    return path, references


def quantize_int8(fp32):
    import onnx
    from onnxruntime.quantization import QuantType, quantize_dynamic

    path, cached = stage("int8")
    if cached:
        return path
    print("Quantizing constant MatMul weights to INT8...", flush=True)
    quantize_dynamic(
        str(fp32), str(path),
        weight_type=QuantType.QInt8,
        op_types_to_quantize=["MatMul"],
        use_external_data_format=True,
        extra_options={"MatMulConstBOnly": True},
    )
    graph = onnx.load(str(path), load_external_data=False)
    if not any(t.data_type == onnx.TensorProto.INT8 for t in graph.graph.initializer):
        raise RuntimeError("Quantization produced no INT8 weight tensors")
    del graph
    finish_stage(path)
    return path


def verify(path, references, kind):
    import numpy as np
    import onnxruntime as ort
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(OUT / "tokenizer")
    options = ort.SessionOptions()
    options.intra_op_num_threads = THREADS
    options.enable_cpu_mem_arena = False
    session = ort.InferenceSession(
        str(path), sess_options=options, providers=["CPUExecutionProvider"],
    )
    results = []
    try:
        for case in references:
            enc = encode(tokenizer, case["query"], case["passage"], "np")
            feed = {name: enc[name].astype(np.int64)
                    for name in ("input_ids", "attention_mask")}
            logits = session.run(["logits"], feed)[0]
            got = float(logits.reshape(-1)[0])
            difference = abs(got - case["logit"])
            print(f"{kind}: tokens={enc['input_ids'].shape[1]}, "
                  f"score={got:.6f}, reference={case['logit']:.6f}, "
                  f"difference={difference:.6f}", flush=True)
            if not np.isfinite(got) or difference > TOLERANCES[kind]:
                raise RuntimeError(
                    f"{kind} verification failed: difference={difference}, "
                    f"tolerance={TOLERANCES[kind]}. No pack built for this variant."
                )
            results.append({**case, "onnx_logit": got, "difference": difference})
    finally:
        del session, tokenizer
        gc.collect()
    return {"status": "passed", "provider": "CPUExecutionProvider",
            "absolute_tolerance": TOLERANCES[kind], "cases": results,
            "scope": "Conversion smoke tests, not a retrieval-quality benchmark"}


def build(pid, source, kind, verification):
    import onnxruntime as ort
    import torch
    import transformers
    from huggingface_hub import hf_hub_download

    # Copy upstream licensing verbatim; do not substitute an assumed license.
    license_path = hf_hub_download(MODEL, "LICENSE", revision=REVISION)
    readme_path = hf_hub_download(MODEL, "README.md", revision=REVISION)
    dst = ROOT / pid
    archive = ROOT / f"{pid}.zip"
    if dst.exists():
        shutil.rmtree(dst)
    archive.unlink(missing_ok=True)
    shutil.copytree(source.parent, dst,
                    ignore=shutil.ignore_patterns("complete.json"))
    for asset in (OUT / "tokenizer").iterdir():
        if asset.is_file():
            shutil.copy2(asset, dst / asset.name)
    shutil.copy2(license_path, dst / "LICENSE")
    shutil.copy2(readme_path, dst / "UPSTREAM_README.md")
    changes = ("Dynamic INT8 quantization of constant MatMul weights; "
               "other tensors may remain floating point.")
    (dst / "CONVERSION_NOTICE.txt").write_text(
        f"Priscilla uses {MODEL} by Alibaba-NLP.\nRevision: {REVISION}\n"
        f"Converted to ONNX by Scriptura Labs.\n{changes}\n"
        "No fine-tuning was performed. See LICENSE and UPSTREAM_README.md.\n",
        encoding="utf-8",
    )
    save_json(dst / "verification.json", verification)
    files = {
        p.relative_to(dst).as_posix(): {"bytes": p.stat().st_size, "sha256": sha256(p)}
        for p in sorted(dst.rglob("*")) if p.is_file()
    }
    save_json(dst / "manifest.json", {
        "format": pid, "model": MODEL, "revision": REVISION, "weights": kind,
        "batch_size": 1, "min_sequence_length": 2,
        "max_sequence_length": MAX_LENGTH, "changes": changes,
        "versions": {"torch": torch.__version__, "onnxruntime": ort.__version__,
                     "transformers": transformers.__version__},
        "files": files,
    })
    check_graph(dst / "model.onnx")
    # ZIP_STORED avoids spending a long time compressing several GB of weights.
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED,
                         allowZip64=True) as bundle:
        for p in sorted(dst.rglob("*")):
            if p.is_file():
                bundle.write(p, p.relative_to(ROOT).as_posix())
    print(f"Built {archive} ({archive.stat().st_size / 2**20:.0f} MiB)", flush=True)


def main():
    # Use this notebook's Python; no GPU package or PyTorch upgrade is needed.
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "--quiet",
        "onnx", "onnxscript", "onnxruntime",
    ])
    import torch

    torch.set_num_threads(THREADS)
    OUT.mkdir(parents=True, exist_ok=True)
    fp32, references = export_fp32()
    verify(fp32, references, "fp32")

    int8 = quantize_int8(fp32)
    report = verify(int8, references, "int8")
    build("priscilla-int8-v1", int8, "int8", report)
    print("DONE. Download priscilla-int8-v1.zip from the output panel.", flush=True)


if __name__ == "__main__":
    main()
