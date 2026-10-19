"""Paste this entire script into ONE Kaggle Python notebook cell and run it.

Internet must be enabled. Uses CPU; requires enough RAM for the FP32 graph.
Exports dynamic-length ONNX, then builds INT8 and FP16 packs plus ZIPs.
Batch size is 1; supported sequence lengths are 2..8192 tokens.
"""

import gc
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

MODEL = "nvidia/llama-nemotron-rerank-1b-v2"
REVISION = "828765652b05bd439c9789d2a6d093db1caa1443"
ROOT = Path("/kaggle/working") if Path("/kaggle/working").exists() else Path.cwd()
# A new directory prevents reuse of the earlier fixed-length export.
OUT = ROOT / "apollos-export-dynamic-v2"
MAX_LENGTH = 8192
THREADS = 4
TOLERANCES = {"fp32": 0.01, "int8": 1.0, "fp16": 0.05}
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
        f"question:{query} \n \n passage:{passage}",
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

    tokenizer = AutoTokenizer.from_pretrained(
        MODEL, revision=REVISION, trust_remote_code=True,
    )
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL, revision=REVISION, trust_remote_code=True,
        dtype=torch.float32,
    ).cpu().eval()
    model.config.use_cache = False

    class LogitsOnly(torch.nn.Module):
        def __init__(self, base):
            super().__init__()
            self.base = base

        def forward(self, input_ids, attention_mask):
            return self.base(
                input_ids=input_ids,
                attention_mask=attention_mask,
                use_cache=False,
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


def prepare_int8_source(fp32):
    import onnx
    from onnxruntime.quantization.onnx_model import ONNXModel

    path, cached = stage("int8-prepared")
    if cached:
        return path
    print("Preparing Gemm/MatMul shapes for INT8 quantization...", flush=True)
    model = ONNXModel(onnx.load(str(fp32)))
    # ORT performs this same rewrite inside quantize_dynamic. Some versions
    # transpose Gemm weights without updating their existing value_info.
    # Do the rewrite first, then synchronize weight metadata with real tensors.
    model.replace_gemm_with_matmul()
    initializers = {tensor.name: tensor for tensor in model.model.graph.initializer}
    for value in model.model.graph.value_info:
        tensor = initializers.get(value.name)
        if tensor is not None:
            correct = onnx.helper.make_tensor_value_info(
                tensor.name, tensor.data_type, list(tensor.dims),
            )
            value.type.CopyFrom(correct.type)
    onnx.save_model(
        model.model, str(path), save_as_external_data=True,
        all_tensors_to_one_file=True, location="model.onnx.data",
        size_threshold=1024,
    )
    del initializers, model
    gc.collect()
    finish_stage(path)
    return path


def quantize_int8(fp32):
    import onnx
    from onnxruntime.quantization import QuantType, quantize_dynamic

    path, cached = stage("int8")
    if cached:
        return path
    prepared = prepare_int8_source(fp32)
    print("Quantizing constant MatMul weights to INT8...", flush=True)
    quantize_dynamic(
        str(prepared), str(path),
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


def convert_fp16(fp32):
    import onnx
    from onnxruntime.transformers.float16 import convert_float_to_float16

    path, cached = stage("fp16")
    if cached:
        return path
    print("Converting FP32 to FP16...", flush=True)
    model = onnx.load(str(fp32))
    half = convert_float_to_float16(
        model, keep_io_types=True, disable_shape_infer=True,
    )
    # Preserve external data instead of trying to embed >2 GB in a protobuf.
    onnx.save_model(
        half, str(path), save_as_external_data=True,
        all_tensors_to_one_file=True, location="model.onnx.data",
        size_threshold=1024,
    )
    del half, model
    gc.collect()
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
               "other tensors may remain floating point." if kind == "int8"
               else "FP16 conversion with FP32 I/O and converter-blocked operations.")
    (dst / "CONVERSION_NOTICE.txt").write_text(
        f"Apollos uses {MODEL} by NVIDIA.\nRevision: {REVISION}\n"
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
    from onnxruntime.capi.onnxruntime_pybind11_state import NotImplemented as ORTNotImplemented

    torch.set_num_threads(THREADS)
    OUT.mkdir(parents=True, exist_ok=True)
    fp32, references = export_fp32()
    verify(fp32, references, "fp32")

    # Package INT8 before starting FP16, so it survives any later FP16 failure.
    int8 = quantize_int8(fp32)
    report = verify(int8, references, "int8")
    build("apollos-int8-v1", int8, "int8", report)

    fp16 = convert_fp16(fp32)
    try:
        report = verify(fp16, references, "fp16")
    except ORTNotImplemented as exc:
        # Only unsupported kernels are allowed to skip execution verification.
        # Graph/type errors and score mismatches still stop the build.
        report = {"status": "not_run", "provider": "CPUExecutionProvider",
                  "reason": str(exc),
                  "required_next_check": "Verify FP16 inference on the target runtime"}
        print("FP16 execution unavailable on this CPU runtime. "
              "Pack will be marked NOT numerically verified.", flush=True)
    build("apollos-fp16-v1", fp16, "fp16", report)
    print("DONE. Download both apollos-*-v1.zip files from the output panel.", flush=True)


if __name__ == "__main__":
    main()
