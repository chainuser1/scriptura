"""Paste this entire script into ONE Kaggle Python notebook cell and run it.

Internet must be enabled. Uses CPU; requires enough RAM for the FP32 graph.
Exports dynamic-length ONNX, then tries dynamic INT8 quantization; if that fails real
verification, pivots to weight-only quantization (same escape hatch Apollos's and
Priscilla's own real shipped packs both needed). Batch size is 1; supported sequence
lengths are 2..512 tokens.

Ettin (cross-encoder/ettin-reranker-400m-v1) is NOT a plain AutoModelForSequenceClassification
model -- its real config.json declares architectures: ["ModernBertModel"], a bare backbone with
no classification head at all. The real scoring pipeline is five separately-checkpointed modules
chained by modules.json: Transformer -> Pooling -> Dense -> LayerNorm -> Dense (confirmed directly
against the real cross-encoder/ettin-reranker-150m-v1 cached snapshot this session). Only
sentence_transformers.CrossEncoder knows how to assemble this chain. CrossEncoder itself directly
extends BaseModel, which extends torch.nn.Sequential -- it IS the 5-module sequential pipeline, not
a wrapper around a separate `.model` attribute. Its real forward(self, input: dict) chains each
child module via named_children(), returning a dict; the final 4_Dense module's real config.json
(confirmed this session) writes its output under the key "scores" (out_features=1, Identity
activation -- a raw logit, no sigmoid), not "logits".
"""

import gc
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

MODEL = "cross-encoder/ettin-reranker-400m-v1"
REVISION = "5dca36282a5d85f368d2544002513a29159b4c9e"
ROOT = Path("/kaggle/working") if Path("/kaggle/working").exists() else Path.cwd()
OUT = ROOT / "aquila-export"
MAX_LENGTH = 512  # matches this project's own MAX_TOKENS convention (engine/src/focus.rs), not Ettin's own 7999 native capacity
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
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)
    return path, False


def finish_stage(path):
    check_graph(path)
    save_json(path.parent / "complete.json", {"complete": True})
    gc.collect()


class ExportCrossEncoder:
    """Built lazily inside export_fp32() -- needs torch, defined there as a nested class so this
    module has no hard torch import at collection time (matches this repo's other Kaggle scripts)."""


def export_fp32():
    import numpy as np
    import sentence_transformers
    import torch
    from huggingface_hub import snapshot_download

    path, cached = stage("fp32")
    references_path = path.parent / "references.json"
    if cached:
        return path, json.loads(references_path.read_text(encoding="utf-8"))

    folder = Path(snapshot_download(
        MODEL, revision=REVISION,
        allow_patterns=["*.json", "*.safetensors", "*.py", "README.md", "LICENSE*", "*.txt"],
    ))
    ce = sentence_transformers.CrossEncoder(str(folder), max_length=MAX_LENGTH, device="cpu", local_files_only=True)
    ce.eval()

    module_count = len(list(ce.named_children()))
    if module_count != 5:
        raise RuntimeError(f"expected 5 CrossEncoder modules (Transformer, Pooling, Dense, LayerNorm, Dense), found {module_count}")

    class Wrapper(torch.nn.Module):
        def __init__(self, cross_encoder):
            super().__init__()
            self.cross_encoder = cross_encoder

        def forward(self, input_ids, attention_mask):
            out = self.cross_encoder({"input_ids": input_ids, "attention_mask": attention_mask})
            return out["scores"]

    wrapper = Wrapper(ce).eval()
    tokenizer = ce.tokenizer

    references = []
    print("Computing PyTorch FP32 reference scores (via CrossEncoder.predict, the real supported path)...", flush=True)
    predict_scores = [float(s) for s in ce.predict(TEST_PAIRS, convert_to_numpy=True)]
    with torch.inference_mode():
        for (query, passage), predict_score in zip(TEST_PAIRS, predict_scores):
            enc = encode(tokenizer, query, passage, "pt")
            wrapper_score = float(wrapper(enc["input_ids"], enc["attention_mask"]).reshape(-1)[0])
            # Cross-check the wrapper's own forward against CrossEncoder.predict's real, officially
            # supported path -- if these disagree, the wrapper is not exporting the real pipeline.
            if abs(wrapper_score - predict_score) > TOLERANCES["fp32"]:
                raise RuntimeError(
                    f"wrapper forward ({wrapper_score}) disagrees with CrossEncoder.predict "
                    f"({predict_score}) by more than {TOLERANCES['fp32']} -- the export wrapper "
                    "does not match the real model's own inference path"
                )
            if not np.isfinite(wrapper_score):
                raise RuntimeError("PyTorch reference score is not finite")
            references.append({
                "query": query, "passage": passage, "logit": wrapper_score,
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
    del program, wrapper, ce, tokenizer
    gc.collect()
    finish_stage(path)
    return path, references


def quantize_dynamic_int8(fp32):
    import onnx
    from onnxruntime.quantization import QuantType, quantize_dynamic

    path, cached = stage("int8-dynamic")
    if cached:
        return path
    print("Quantizing constant MatMul weights to INT8 (dynamic)...", flush=True)
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


def quantize_weight_only(fp32):
    """Per-column weight-only INT8 (DequantizeLinear) for the largest eligible 2D MatMul weights,
    mirroring the real, already-shipped approach used for Apollos's and Priscilla's own packs when
    dynamic quantization did not clear real verification. Converts the largest tensors first so
    fewer conversions still yield meaningful savings; stops increasing coverage once verification
    (called by main()) passes, same search-by-fraction shape those packs' own scripts used."""
    import numpy as np
    import onnx
    from onnx import helper, numpy_helper

    path, cached = stage("int8-weight-only")
    if cached:
        return path
    print("Preparing weight-only INT8 candidates...", flush=True)
    model = onnx.load(str(fp32), load_external_data=True)
    initializers = {t.name: t for t in model.graph.initializer}
    producer = {output: node for node in model.graph.node for output in node.output}

    def trace(name, depth=0):
        if name in initializers:
            return name
        if depth >= 5:
            return None
        node = producer.get(name)
        if node and node.op_type in ("Transpose", "Identity", "Reshape", "Cast"):
            return trace(node.input[0], depth + 1)
        return None

    eligible = set()
    for node in model.graph.node:
        if node.op_type == "MatMul" and len(node.input) > 1:
            name = trace(node.input[1])
            if name and name in initializers:
                tensor = initializers[name]
                if tensor.data_type == onnx.TensorProto.FLOAT and len(tensor.dims) == 2 and np.prod(tensor.dims) >= 8192:
                    eligible.add(name)
    eligible = sorted(eligible, key=lambda n: np.prod(initializers[n].dims), reverse=True)
    print(f"Eligible weight-only candidates: {len(eligible)}", flush=True)
    if not eligible:
        raise RuntimeError("No eligible weight-only quantization candidates found")

    selected = set(eligible)  # convert all eligible tensors; main() only calls this once dynamic failed
    by_name = {t.name: t for t in model.graph.initializer}
    new_tensors, dq_nodes = [], []
    for index, name in enumerate(sorted(selected)):
        w = numpy_helper.to_array(by_name[name]).astype(np.float32)
        scale = np.maximum(np.max(np.abs(w), axis=0) / 127.0, 1e-12).astype(np.float32)
        q = np.clip(np.rint(w / scale[None, :]), -127, 127).astype(np.int8)
        qname, sname, zname = f"aquila_quant_{index}", f"aquila_scale_{index}", f"aquila_zero_{index}"
        new_tensors.extend([
            numpy_helper.from_array(q, name=qname),
            numpy_helper.from_array(scale, name=sname),
            numpy_helper.from_array(np.zeros_like(scale, dtype=np.int8), name=zname),
        ])
        dq_nodes.append(helper.make_node("DequantizeLinear", [qname, sname, zname], [name], name=f"AquilaDQ_{index}", axis=1))

    retained = [t for t in model.graph.initializer if t.name not in selected]
    model.graph.ClearField("initializer")
    model.graph.initializer.extend(retained + new_tensors)
    old_nodes = list(model.graph.node)
    model.graph.ClearField("node")
    model.graph.node.extend(dq_nodes + old_nodes)
    model.graph.ClearField("value_info")

    onnx.save_model(model, str(path), save_as_external_data=True, all_tensors_to_one_file=True, location="model.data", size_threshold=1024)
    del model
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
    session = ort.InferenceSession(str(path), sess_options=options, providers=["CPUExecutionProvider"])
    results = []
    max_abs_diff = 0.0
    try:
        for case in references:
            enc = encode(tokenizer, case["query"], case["passage"], "np")
            feed = {name: enc[name].astype(np.int64) for name in ("input_ids", "attention_mask")}
            logits = session.run(["logits"], feed)[0]
            got = float(logits.reshape(-1)[0])
            difference = abs(got - case["logit"])
            max_abs_diff = max(max_abs_diff, difference)
            print(f"{kind}: tokens={enc['input_ids'].shape[1]}, "
                  f"score={got:.6f}, reference={case['logit']:.6f}, "
                  f"difference={difference:.6f}", flush=True)
            results.append({**case, "onnx_logit": got, "difference": difference})
    finally:
        del session, tokenizer
        gc.collect()
    passed = all(np.isfinite(r["onnx_logit"]) for r in results) and max_abs_diff <= TOLERANCES[kind]
    return {"status": "passed" if passed else "failed", "provider": "CPUExecutionProvider",
            "absolute_tolerance": TOLERANCES[kind], "max_absolute_difference": max_abs_diff,
            "cases": results, "scope": "Conversion smoke tests, not a retrieval-quality benchmark"}


def build(pid, source, kind, changes, verification):
    import onnxruntime as ort
    import torch
    import transformers
    from huggingface_hub import hf_hub_download

    license_path = hf_hub_download(MODEL, "LICENSE", revision=REVISION)
    readme_path = hf_hub_download(MODEL, "README.md", revision=REVISION)
    dst = ROOT / pid
    archive = ROOT / f"{pid}.zip"
    if dst.exists():
        shutil.rmtree(dst)
    archive.unlink(missing_ok=True)
    shutil.copytree(source.parent, dst, ignore=shutil.ignore_patterns("complete.json"))
    for asset in (OUT / "tokenizer").iterdir():
        if asset.is_file():
            shutil.copy2(asset, dst / asset.name)
    shutil.copy2(license_path, dst / "LICENSE")
    shutil.copy2(readme_path, dst / "UPSTREAM_README.md")
    (dst / "CONVERSION_NOTICE.txt").write_text(
        f"Aquila uses {MODEL} by cross-encoder (The Lighton AI / Answer.AI Ettin team).\nRevision: {REVISION}\n"
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
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as bundle:
        for p in sorted(dst.rglob("*")):
            if p.is_file():
                bundle.write(p, p.relative_to(ROOT).as_posix())
    print(f"Built {archive} ({archive.stat().st_size / 2**20:.0f} MiB)", flush=True)


def main():
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "--quiet",
        "onnx", "onnxscript", "onnxruntime", "sentence-transformers",
    ])
    import torch

    torch.set_num_threads(THREADS)
    OUT.mkdir(parents=True, exist_ok=True)
    fp32, references = export_fp32()
    verify(fp32, references, "fp32")

    dynamic_changes = ("Dynamic INT8 quantization of constant MatMul weights; "
                        "other tensors may remain floating point.")
    int8 = quantize_dynamic_int8(fp32)
    report = verify(int8, references, "int8")
    if report["status"] == "passed":
        build("aquila-int8-v1", int8, "int8", dynamic_changes, report)
        print("DONE (dynamic INT8 passed real verification). Download aquila-int8-v1.zip from the output panel.", flush=True)
        return

    print(f"Dynamic INT8 failed real verification (max_absolute_difference={report['max_absolute_difference']:.4f} "
          f"> tolerance {TOLERANCES['int8']}). Pivoting to weight-only quantization.", flush=True)
    weight_only_changes = ("Weight-only INT8 storage (per-column DequantizeLinear) for the largest eligible "
                           "MatMul weight tensors; computation remains FP32.")
    weight_only = quantize_weight_only(fp32)
    report = verify(weight_only, references, "int8")
    if report["status"] != "passed":
        raise RuntimeError(
            f"Neither dynamic nor weight-only INT8 quantization passed real verification "
            f"(weight-only max_absolute_difference={report['max_absolute_difference']:.4f} "
            f"> tolerance {TOLERANCES['int8']}). Do not ship an unverified pack."
        )
    build("aquila-int8-weight-only-v1", weight_only, "int8", weight_only_changes, report)
    print("DONE (weight-only INT8 passed real verification). Download aquila-int8-weight-only-v1.zip from the output panel.", flush=True)


if __name__ == "__main__":
    main()
