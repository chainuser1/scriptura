//! Answer focus (the BGE reranker as ONNX): pair tokenization, scores against the fp32 reference
//! (test/golden/answer_focus_pairs.json), CPU and graphics devices, and the engine's `focus` and `device_trial` requests.
//! Skipped without the built packs (tool/build_answer_focus_pack.py).

use scripture_engine::{
    engine::{Config, Engine},
    focus::{gpu_available, Focus, RerankerFamily},
};
use serde_json::{json, Value};
use std::path::PathBuf;
use std::sync::atomic::AtomicBool;
use std::sync::{Mutex, MutexGuard, OnceLock};

fn root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).parent().unwrap().to_path_buf()
}

fn golden() -> Value {
    serde_json::from_str(&std::fs::read_to_string(root().join("test/golden/answer_focus_pairs.json")).unwrap()).unwrap()
}

fn pack(variant: &str) -> Option<PathBuf> {
    let d = root().join(format!("generated-artifacts/answer-focus-{variant}-v1"));
    if d.join("model.onnx").exists() {
        Some(d)
    } else {
        eprintln!("skipped: {} not built", d.display());
        None
    }
}

/// One loaded model per variant for all tests (each is hundreds of MB; tests run in parallel).
fn shared(variant: &'static str) -> Option<MutexGuard<'static, Focus>> {
    static INT8: OnceLock<Option<Mutex<Focus>>> = OnceLock::new();
    static FP16: OnceLock<Option<Mutex<Focus>>> = OnceLock::new();
    let cell = if variant == "int8" { &INT8 } else { &FP16 };
    cell.get_or_init(|| pack(variant).map(|d| Mutex::new(Focus::open(&d.join("model.onnx"), &d.join("tokenizer.json"), 4, variant == "fp16", RerankerFamily::Ezra).unwrap())))
        .as_ref()
        .map(|m| m.lock().unwrap_or_else(|e| e.into_inner()))
}

/// Apollos's own shared model, mirroring [shared] above. Apollos only ships as fp16/GPU; skips gracefully (same
/// as [pack]) if `generated-artifacts/apollos-fp16-v1` isn't built in this environment.
fn shared_apollos() -> Option<MutexGuard<'static, Focus>> {
    static APOLLOS: OnceLock<Option<Mutex<Focus>>> = OnceLock::new();
    let d = root().join("generated-artifacts/apollos-fp16-v1");
    APOLLOS
        .get_or_init(|| {
            if !d.join("model.onnx").exists() {
                eprintln!("skipped: {} not built", d.display());
                return None;
            }
            Some(Mutex::new(Focus::open(&d.join("model.onnx"), &d.join("tokenizer.json"), 4, true, RerankerFamily::Apollos).unwrap()))
        })
        .as_ref()
        .map(|m| m.lock().unwrap_or_else(|e| e.into_inner()))
}

/// Priscilla's own shared model, mirroring [shared_apollos] above. Skips gracefully (same as [pack]) if
/// `generated-artifacts/priscilla-int8-v1` isn't built in this environment.
fn shared_priscilla() -> Option<MutexGuard<'static, Focus>> {
    static PRISCILLA: OnceLock<Option<Mutex<Focus>>> = OnceLock::new();
    let d = root().join("generated-artifacts/priscilla-int8-v1");
    PRISCILLA
        .get_or_init(|| {
            if !d.join("model.onnx").exists() {
                eprintln!("skipped: {} not built", d.display());
                return None;
            }
            Some(Mutex::new(Focus::open(&d.join("model.onnx"), &d.join("tokenizer.json"), 4, false, RerankerFamily::Priscilla).unwrap()))
        })
        .as_ref()
        .map(|m| m.lock().unwrap_or_else(|e| e.into_inner()))
}

/// Scores a pack's own `verification.json` cases through [Focus::score], one call per query so the
/// two-passage query goes through as a multi-text batch, and checks each against the reference `logit` within
/// the pack's recorded `absolute_tolerance`.
fn matches_pack_verification(f: &mut Focus, dir: &std::path::Path) {
    let v: Value = serde_json::from_str(&std::fs::read_to_string(dir.join("verification.json")).unwrap()).unwrap();
    let tol = v["absolute_tolerance"].as_f64().unwrap() as f32;
    let cases = v["cases"].as_array().unwrap();
    let mut queries: Vec<&str> = cases.iter().map(|c| c["query"].as_str().unwrap()).collect();
    queries.dedup();
    assert!(queries.len() < cases.len(), "no query has more than one passage, so no call would batch");
    for q in queries {
        let group: Vec<&Value> = cases.iter().filter(|c| c["query"] == q).collect();
        let texts: Vec<&str> = group.iter().map(|c| c["passage"].as_str().unwrap()).collect();
        let got = f.score(q, &texts, &AtomicBool::new(false)).unwrap();
        for (c, g) in group.iter().zip(&got) {
            let want = c["logit"].as_f64().unwrap() as f32;
            assert!((g - want).abs() <= tol, "{}: {q:?} / {:?}: got {g}, want {want} (tolerance {tol})", dir.display(), c["passage"]);
        }
    }
}

#[test]
fn apollos_on_the_graphics_chip_scores_several_texts_in_one_call() {
    let Some(mut f) = shared_apollos() else { return };
    let got = f.score("Why?", &["Jesus wept.", "And Seth begat Enos.", "Faith is the substance of things hoped for."], &AtomicBool::new(false)).unwrap();
    assert_eq!(got.len(), 3);
    // score() moves to the CPU for good on a graphics error, so success alone would hide a batch the graph rejects.
    // Checked against gpu_available(), not the device before scoring, so an earlier test's fallback cannot mask it.
    assert_eq!(f.device(), if gpu_available() { "gpu" } else { "cpu" }, "Apollos fell off the graphics chip while scoring");
}

#[test]
fn apollos_fp16_matches_its_pack_verification() {
    let Some(mut f) = shared_apollos() else { return };
    matches_pack_verification(&mut f, &root().join("generated-artifacts/apollos-fp16-v1"));
    assert_eq!(f.device(), if gpu_available() { "gpu" } else { "cpu" }, "Apollos fell off the graphics chip while scoring");
}

#[test]
fn apollos_int8_matches_its_pack_verification() {
    let d = root().join("generated-artifacts/apollos-int8-v1");
    if !d.join("model.onnx").exists() {
        eprintln!("skipped: {} not built", d.display());
        return;
    }
    // Opened here, not shared: dropped after this test so two ~2 GB Apollos models are not held at once.
    let mut f = Focus::open(&d.join("model.onnx"), &d.join("tokenizer.json"), 4, false, RerankerFamily::Apollos).unwrap();
    matches_pack_verification(&mut f, &d);
}

#[test]
fn priscilla_int8_matches_its_pack_verification() {
    let Some(mut f) = shared_priscilla() else { return };
    matches_pack_verification(&mut f, &root().join("generated-artifacts/priscilla-int8-v1"));
    assert_eq!(f.device(), "cpu");
}

fn priscilla_golden() -> Value {
    serde_json::from_str(&std::fs::read_to_string(root().join("test/golden/priscilla_pairs.json")).unwrap()).unwrap()
}

#[test]
fn priscilla_pairs_tokenize_like_python() {
    let Some(f) = shared_priscilla() else { return };
    for p in priscilla_golden()["pairs"].as_array().unwrap() {
        let want: Vec<u32> = p["input_ids"].as_array().unwrap().iter().map(|x| x.as_u64().unwrap() as u32).collect();
        assert_eq!(f.encode(p["query"].as_str().unwrap(), p["text"].as_str().unwrap()).unwrap(), want);
    }
}

fn scores(f: &mut Focus) -> Vec<f32> {
    let g = golden();
    g["pairs"]
        .as_array()
        .unwrap()
        .iter()
        .map(|p| f.score(p["query"].as_str().unwrap(), &[p["text"].as_str().unwrap()], &AtomicBool::new(false)).unwrap()[0])
        .collect()
}

fn reference() -> Vec<f32> {
    golden()["pairs"].as_array().unwrap().iter().map(|p| p["score"].as_f64().unwrap() as f32).collect()
}

#[test]
fn pairs_tokenize_like_python() {
    let Some(f) = shared("int8") else { return };
    for p in golden()["pairs"].as_array().unwrap() {
        let want: Vec<u32> = p["input_ids"].as_array().unwrap().iter().map(|x| x.as_u64().unwrap() as u32).collect();
        assert_eq!(f.encode(p["query"].as_str().unwrap(), p["text"].as_str().unwrap()).unwrap(), want);
    }
}

#[test]
fn long_passages_are_truncated_to_the_model_limit() {
    let Some(f) = shared("int8") else { return };
    let long = "And it came to pass ".repeat(400);
    assert_eq!(f.encode("What happened?", &long).unwrap().len(), 512);
}

#[test]
fn apollos_concatenates_question_and_passage_as_one_string() {
    let Some(f) = shared_apollos() else { return };
    let ids = f.encode("What is the capital of France?", "Paris is the capital of France.").unwrap();
    // Re-tokenize the same literal string the Kaggle pipeline used and compare, rather than hand-building IDs.
    let expected_text = "question:What is the capital of France? \n \n passage:Paris is the capital of France.";
    let direct = f.tokenizer_encode_single(expected_text).unwrap();
    assert_eq!(ids, direct);
}

#[test]
fn int8_on_the_cpu_matches_the_reference() {
    let Some(mut f) = shared("int8") else { return };
    assert_eq!(f.device(), "cpu");
    let (got, want) = (scores(&mut f), reference());
    for (g, w) in got.iter().zip(&want) {
        assert!((g - w).abs() <= 1.0, "{got:?} vs {want:?}");
    }
    assert!(got[0].min(got[1]) - got[2] > 3.0, "{got:?}");
}

#[test]
fn a_batch_scores_like_one_by_one() {
    let Some(mut f) = shared("int8") else { return };
    let q = "How can I know that God has forgiven me?";
    let texts = ["If we confess our sins, he is faithful and just to forgive us our sins.", "Jesus wept.", "And Seth lived an hundred and five years, and begat Enos."];
    let batch = f.score(q, &texts, &AtomicBool::new(false)).unwrap();
    for (t, b) in texts.iter().zip(&batch) {
        let one = f.score(q, &[*t], &AtomicBool::new(false)).unwrap()[0];
        assert!((one - b).abs() < 1e-3, "padding changed a score: {one} vs {b}");
    }
    assert!(f.score(q, &[], &AtomicBool::new(false)).unwrap().is_empty());
}

#[test]
fn fp16_on_the_graphics_chip_matches_the_reference_or_falls_back() {
    let Some(mut f) = shared("fp16") else { return };
    assert_eq!(f.device(), if gpu_available() { "gpu" } else { "cpu" });
    let (got, want) = (scores(&mut f), reference());
    for (g, w) in got.iter().zip(&want) {
        assert!((g - w).abs() <= 0.1, "{got:?} vs {want:?}");
    }
    // A graphics failure at run time (driver reset, device removed) moves the model to the CPU once, for good.
    f.fall_back_to_cpu().unwrap();
    assert_eq!(f.device(), "cpu");
    let again = scores(&mut f);
    for (g, w) in again.iter().zip(&want) {
        assert!((g - w).abs() <= 0.1, "after fallback {again:?} vs {want:?}");
    }
}

#[test]
fn a_cancelled_focus_stops() {
    let Some(mut f) = shared("int8") else { return };
    let texts = vec!["Jesus wept."; 20];
    assert_eq!(f.score("Why?", &texts, &AtomicBool::new(true)).unwrap_err(), "cancelled");
}

fn engine(focus: Option<(PathBuf, &str)>) -> Option<Engine> {
    let ext = root().join(".artifact-staging/import-application-v1/extracted");
    let model = root().join("generated-artifacts/onnx-int8/bge_m3_multi_int8_matmul.onnx");
    if !model.exists() {
        eprintln!("skipped: encoder not present");
        return None;
    }
    let mut cfg = json!({
        "retrieval_dir": ext.join("scripture-retrieval-english-v1"),
        "head_npz": ext.join("scripture-genome-question-hidden4096-optimized/head_fp16.npz"),
        "encoder_model": model,
        "tokenizer_json": ext.join("bge-m3-pinned/tokenizer.json"),
        "profiles": {"compass": [1, 1, 0, 1], "lantern": [1, 1, 0, 1]},
        "default_profile": "compass",
        "fallback_without_thread": "lantern",
        "threads": 4,
    });
    if let Some((d, device)) = focus {
        cfg["focus_model"] = json!(d.join("model.onnx"));
        cfg["focus_tokenizer"] = json!(d.join("tokenizer.json"));
        cfg["focus_device"] = json!(device);
    }
    Some(Engine::open(serde_json::from_value::<Config>(cfg).unwrap()).unwrap())
}

#[test]
fn the_engine_answers_focus_requests() {
    let Some(d) = pack("int8") else { return };
    let Some(e) = engine(Some((d, "cpu"))) else { return };
    let r = e.handle(&json!({"op": "focus", "query": "Why?", "texts": ["Jesus wept.", "And Seth begat Enos."], "request_id": 7}));
    assert_eq!(r["scores"].as_array().unwrap().len(), 2, "{r}");
    assert_eq!(r["device"], "cpu");
    assert!(r["ms"].as_f64().unwrap() > 0.0);
    assert_eq!(r["request_id"], 7);
    let bad = e.handle(&json!({"op": "focus", "query": "Why?"}));
    assert_eq!(bad["error"]["code"], "invalid_input", "{bad}");
}

#[test]
fn without_focus_the_engine_says_so_and_still_searches() {
    let Some(e) = engine(None) else { return };
    let r = e.handle(&json!({"op": "focus", "query": "Why?", "texts": ["Jesus wept."]}));
    assert_eq!(r["error"]["code"], "focus_unavailable", "{r}");
    assert!(e.handle(&json!({"op": "semantic", "query": "faith", "top_k": 3}))["hits"].as_array().unwrap().len() == 3);
}

#[test]
fn a_broken_focus_model_does_not_stop_the_engine() {
    let bogus = root().join("engine/Cargo.toml"); // not a model
    let Some(e) = engine(Some((bogus.parent().unwrap().to_path_buf(), "cpu"))) else { return };
    let r = e.handle(&json!({"op": "focus", "query": "Why?", "texts": ["Jesus wept."]}));
    assert_eq!(r["error"]["code"], "focus_unavailable", "{r}");
}

#[test]
fn the_device_trial_reports_cpu_time_and_graphics() {
    let Some(e) = engine(None) else { return };
    let r = e.handle(&json!({"op": "device_trial"}));
    assert!(r["cpu_ms"].as_f64().unwrap() > 0.0, "{r}");
    assert_eq!(r["gpu"].as_bool().unwrap(), gpu_available());
}

#[test]
fn the_model_loads_on_first_use_not_when_the_engine_opens() {
    let Some(d) = pack("int8") else { return };
    let Some(e) = engine(Some((d, "cpu"))) else { return };
    assert_eq!(e.handle(&json!({"op": "info"}))["focus"], "not loaded", "a phone must not hold the model until it is used");
    e.handle(&json!({"op": "focus", "query": "Why?", "texts": ["Jesus wept."]}));
    assert_eq!(e.handle(&json!({"op": "info"}))["focus"], "cpu");
}

#[test]
fn the_device_trial_can_skip_the_graphics_probe() {
    let Some(e) = engine(None) else { return };
    let r = e.handle(&json!({"op": "device_trial", "probe_gpu": false}));
    assert_eq!(r["gpu"], false, "{r}");
    assert!(r["cpu_ms"].as_f64().unwrap() > 0.0);
}
