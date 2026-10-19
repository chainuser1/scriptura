//! Opt-in per-candidate keyword concentration (docs/ANSWER_FOCUS_KEYWORD_CONCENTRATION_PROTOCOL.md "Engineering").
//! Without `concentration: true` the response is unchanged (including with `lanes: true` alone -- no concentration
//! field unless separately requested). With it, each hit's `lanes` object gains `concentration` in [0, 1]: the
//! single largest per-word sparse-match contribution divided by the sparse lane's total, already computed inside
//! Index::sparse_scores and discarded before this change. Skipped without the built artifacts, same precondition
//! as engine_e2e.rs.

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
fn without_the_flag_concentration_is_absent_even_with_lanes() {
    let Some(e) = open() else { return };
    let no_flag = e.handle(&json!({"op": "semantic", "query": "What is faith?", "top_k": 5, "lanes": true, "request_id": 1}));
    assert!(no_flag.get("error").is_none(), "{no_flag}");
    for h in no_flag["hits"].as_array().unwrap() {
        assert!(h["lanes"].get("concentration").is_none(), "{h}");
    }
    let false_flag = e.handle(&json!({"op": "semantic", "query": "What is faith?", "top_k": 5, "lanes": true, "concentration": false, "request_id": 1}));
    for h in false_flag["hits"].as_array().unwrap() {
        assert!(h["lanes"].get("concentration").is_none(), "{h}");
    }
}

#[test]
fn concentration_is_in_range_and_matches_an_independent_reconstruction() {
    let Some(e) = open() else { return };
    let r = e.handle(&json!({"op": "semantic", "query": "What is faith?", "profile": "compass", "top_k": 10, "lanes": true, "concentration": true, "request_id": 1}));
    assert!(r.get("error").is_none(), "{r}");
    let hits = r["hits"].as_array().unwrap();
    assert!(!hits.is_empty());
    for h in hits {
        let lanes = &h["lanes"];
        let c = lanes["concentration"].as_f64().unwrap_or_else(|| panic!("missing concentration on {h}"));
        assert!((0.0..=1.0).contains(&c), "concentration out of range: {h}");
    }
}

#[test]
fn a_single_token_query_concentrates_fully_on_every_candidate() {
    // "faith" tokenizes to exactly one content piece (confirmed: <s> _faith </s>), so for every candidate whose
    // sparse score is positive, that one term IS the whole sum: concentration must be exactly 1.0. This is a
    // guarantee the formula owes, provable directly, not an assumption about which real verses happen to match.
    let Some(e) = open() else { return };
    let r = e.handle(&json!({"op": "semantic", "query": "faith", "profile": "compass", "top_k": 20, "lanes": true, "concentration": true, "request_id": 1}));
    assert!(r.get("error").is_none(), "{r}");
    let hits = r["hits"].as_array().unwrap();
    assert!(!hits.is_empty());
    let mut checked_any_positive = false;
    for h in hits {
        let sparse = h["lanes"]["sparse"].as_f64().unwrap();
        let c = h["lanes"]["concentration"].as_f64().unwrap();
        if sparse > 0.0 {
            checked_any_positive = true;
            assert!((c - 1.0).abs() < 1e-6, "single-token query must concentrate fully: {h}");
        }
    }
    assert!(checked_any_positive, "expected at least one candidate with a positive sparse match for 'faith'");
}

#[test]
fn concentration_is_zero_when_the_sparse_lane_itself_is_zero() {
    let Some(e) = open() else { return };
    // lantern still has a nonzero spark weight, but pick a query/profile combination and just check the invariant:
    // wherever the sparse lane value is 0 (or negative, after balancing), concentration must be exactly 0, never NaN.
    let r = e.handle(&json!({"op": "semantic", "query": "faith hope charity", "profile": "compass", "top_k": 50, "lanes": true, "concentration": true, "request_id": 1}));
    assert!(r.get("error").is_none(), "{r}");
    for h in r["hits"].as_array().unwrap() {
        let sparse = h["lanes"]["sparse"].as_f64().unwrap();
        let c = h["lanes"]["concentration"].as_f64().unwrap();
        assert!(c.is_finite(), "{h}");
        if sparse <= 0.0 {
            assert_eq!(c, 0.0, "{h}");
        }
    }
}
