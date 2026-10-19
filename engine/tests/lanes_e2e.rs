//! Opt-in per-candidate lane scores on search/semantic (docs/ANSWER_FOCUS_RICHER_INPUTS_PROTOCOL.md "Engineering").
//! Without `lanes: true` the response is byte-identical to today; with it, each hit also carries the z-scored
//! dense/sparse/colbert/genome values that search_balanced already computes before fusing them into `score`.
//! Skipped without the built artifacts, same precondition as engine_e2e.rs.

use scripture_engine::engine::{Config, Engine};
use serde_json::{json, Value};
use std::path::PathBuf;

fn root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).parent().unwrap().to_path_buf()
}

fn read(p: &str) -> Value {
    serde_json::from_str(&std::fs::read_to_string(root().join(p)).unwrap()).unwrap()
}

fn open() -> Option<Engine> {
    let ext = root().join(".artifact-staging/import-application-v1/extracted");
    let rel = root().join("generated-artifacts/release");
    let model = root().join("generated-artifacts/onnx-int8/bge_m3_multi_int8_matmul.onnx");
    let pack = root().join("generated-artifacts/colbert-pack-v1");
    if !model.exists() || !pack.exists() || !rel.join("catalog.db").exists() {
        eprintln!("skipped: artifacts not present");
        return None;
    }
    let profiles = read("tool/data/fusion_profiles.json");
    let p = profiles["profiles"].as_object().unwrap();
    let map: serde_json::Map<String, Value> = p
        .iter()
        .map(|(k, v)| (k.clone(), json!([v["echo"], v["spark"], v["thread"], v["root"]])))
        .collect();
    let cfg = json!({
        "retrieval_dir": ext.join("scripture-retrieval-english-v1"),
        "head_npz": ext.join("scripture-genome-question-hidden4096-optimized/head_fp16.npz"),
        "encoder_model": model,
        "tokenizer_json": ext.join("bge-m3-pinned/tokenizer.json"),
        "pack_dir": pack,
        "phrase_db": rel.join("phrase-index.db"),
        "catalog_db": rel.join("catalog.db"),
        "profiles": map,
        "default_profile": "compass",
        "fallback_without_thread": "lantern",
        "identity": {"base_model_revision": "r", "fusion": {"lane_k": 200}},
    });
    Some(Engine::open(serde_json::from_value::<Config>(cfg).unwrap()).unwrap())
}

#[test]
fn without_the_flag_the_response_is_unchanged() {
    let Some(e) = open() else { return };
    let with_no_flag = e.handle(&json!({"op": "semantic", "query": "What is faith?", "top_k": 10, "request_id": 1}));
    let with_false = e.handle(&json!({"op": "semantic", "query": "What is faith?", "top_k": 10, "lanes": false, "request_id": 1}));
    assert!(with_no_flag["hits"][0].get("lanes").is_none(), "{with_no_flag}");
    assert!(with_false["hits"][0].get("lanes").is_none(), "{with_false}");
    // identical in every other field too (score, verse_id, profile, candidates, configuration_id)
    let mut a = with_no_flag.clone();
    let mut b = with_false.clone();
    a.as_object_mut().unwrap().remove("timings_ms");
    b.as_object_mut().unwrap().remove("timings_ms");
    assert_eq!(a, b);
}

/// [echo, spark, thread, root] for `profile`, read from the existing `info` op (never invents a new response field).
fn weights_of(e: &Engine, profile: &str) -> (f64, f64, f64, f64) {
    let info = e.handle(&json!({"op": "info"}));
    let p = info["profiles"].as_array().unwrap().iter().find(|p| p["id"] == profile).unwrap();
    let w = p["weights"].as_array().unwrap();
    (w[0].as_f64().unwrap(), w[1].as_f64().unwrap(), w[2].as_f64().unwrap(), w[3].as_f64().unwrap())
}

#[test]
fn lanes_reconstruct_the_fused_score_with_colbert() {
    let Some(e) = open() else { return };
    let (we, ws, wt, wr) = weights_of(&e, "compass");
    let r = e.handle(&json!({"op": "semantic", "query": "What is faith?", "profile": "compass", "top_k": 10, "lanes": true, "request_id": 1}));
    assert!(r.get("error").is_none(), "{r}");
    let hits = r["hits"].as_array().unwrap();
    assert!(!hits.is_empty());
    for h in hits {
        let lanes = h.get("lanes").unwrap_or_else(|| panic!("missing lanes on {h}"));
        let (d, s, c, g) = (
            lanes["dense"].as_f64().unwrap(),
            lanes["sparse"].as_f64().unwrap(),
            lanes["colbert"].as_f64().unwrap(),
            lanes["genome"].as_f64().unwrap(),
        );
        let reconstructed = we * d + ws * s + wt * c + wr * g;
        let score = h["score"].as_f64().unwrap();
        assert!((reconstructed - score).abs() < 1e-6, "lanes {lanes} do not reconstruct score {score} (got {reconstructed})");
    }
}

#[test]
fn lanes_reconstruct_the_fused_score_without_colbert() {
    // lantern has thread weight 0 (Compass's own no-index fallback): colbert lane must be 0.0 for every candidate,
    // matching how search_balanced already treats zc when w.thread == 0.0, and the reconstruction must still hold.
    let Some(e) = open() else { return };
    let (we, ws, wt, wr) = weights_of(&e, "lantern");
    assert_eq!(wt, 0.0, "lantern is expected to have thread weight 0");
    let r = e.handle(&json!({"op": "semantic", "query": "What is faith?", "profile": "lantern", "top_k": 10, "lanes": true, "request_id": 1}));
    assert!(r.get("error").is_none(), "{r}");
    let hits = r["hits"].as_array().unwrap();
    assert!(!hits.is_empty());
    for h in hits {
        let lanes = &h["lanes"];
        assert_eq!(lanes["colbert"].as_f64().unwrap(), 0.0, "{h}");
        let reconstructed = we * lanes["dense"].as_f64().unwrap() + ws * lanes["sparse"].as_f64().unwrap() + wr * lanes["genome"].as_f64().unwrap();
        assert!((reconstructed - h["score"].as_f64().unwrap()).abs() < 1e-6, "{h}");
    }
}
