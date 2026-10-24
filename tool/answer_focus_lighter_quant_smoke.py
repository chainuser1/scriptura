"""Quantization smoke check for gte-reranker-modernbert-base and the two Ettin reranker sizes: runs on Kaggle,
not locally -- see .kaggle-package/answer_focus_lighter_quant_smoke_kaggle.py for the actual script and
instructions. This file exists only as a pointer, because the local environment cannot run it directly.

Why Kaggle, not here: Ettin's repos require transformers>=5.0 (a tokenizer-backend redesign; see this repo's
ANSWER_FOCUS_CHALLENGERS_ROUND2_PROTOCOL.md decision log), which this machine's local Python does not have,
and this task additionally needs optimum[onnxruntime] for the ONNX export + dynamic-quantization step, which
is also not installed locally. Rather than upgrade the shared system Python (risking every other project on
this machine) or build a disposable local venv, this reuses the project's existing Kaggle/GPU workflow
pattern (see .kaggle-package/answer_focus_challengers_kaggle.py, the original Qwen/Nemotron scoring script).

Results land in local-benchmarks/answer-focus-lighter-quant-smoke/<model>.json after downloading
/kaggle/working/quant-smoke/ from the Kaggle notebook and copying its contents here.
"""
print(__doc__)
