//! Engine facade end to end through the same JSON interface the C ABI exposes: routing, filters, cancellation,
//! typed errors, configuration identity parity, entity linking parity.

use scripture_engine::{engine::{Config, Engine}, entities::PeopleIndex, identity};
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
        "entities_db": root().join(".artifact-staging/entities.db"),
        "topics_db": root().join("generated-artifacts/topics-pack-v1/topics.db"),
        "profiles": map,
        "default_profile": "compass",
        "fallback_without_thread": "lantern",
        "identity": {"base_model_revision": "r", "fusion": {"lane_k": 200}},
    });
    Some(Engine::open(serde_json::from_value::<Config>(cfg).unwrap()).unwrap())
}

#[test]
fn entity_links_match_python_cases() {
    let db = root().join(".artifact-staging/entities.db");
    if !db.exists() {
        return eprintln!("skipped: entities.db not exported");
    }
    let idx = PeopleIndex::open(&db).unwrap();
    let mut bad = Vec::new();
    for c in read("test/golden/entity_link_cases.json").as_array().unwrap() {
        let q = c["query"].as_str().unwrap();
        let l = idx.link(q);
        let want_first = c["first"].as_str();
        if l.status != c["status"].as_str().unwrap() || (want_first.is_some() && l.candidates.first().map(String::as_str) != want_first) {
            bad.push(format!("{q:?}: {l:?}"));
        }
    }
    assert!(bad.is_empty(), "{}", bad.join("\n"));
    assert!(!idx.link("Who is Jesus Christ?").filter);
}

#[test]
fn place_links_match_python_cases() {
    let db = root().join("generated-artifacts/entities-pack-v1/entities.db");
    if !db.exists() {
        return eprintln!("skipped: entities pack not built");
    }
    let idx = PeopleIndex::open(&db).unwrap();
    let mut bad = Vec::new();
    for c in read("test/golden/entity_place_cases.json").as_array().unwrap() {
        let q = c["query"].as_str().unwrap();
        let l = idx.link(q);
        let want_first = c["first"].as_str();
        if l.status != c["status"].as_str().unwrap() || (want_first.is_some() && l.candidates.first().map(String::as_str) != want_first) {
            bad.push(format!("{q:?}: {l:?}"));
        }
    }
    assert!(bad.is_empty(), "{}", bad.join("
"));
}

#[test]
fn topic_lane_matches_python_reference() {
    let Some(e) = open() else { return };
    let golden = read("test/golden/topics_similar.json");
    if !root().join("generated-artifacts/topics-pack-v1/topics.db").exists() {
        return eprintln!("skipped: topics pack not built");
    }
    assert_eq!(e.info()["topics"], true);
    let mut bad = Vec::new();
    for c in golden["cases"].as_array().unwrap() {
        let mut req = json!({"op": "similar", "verse_id": c["verse_id"], "top_k": c["top_k"]});
        if !c["filter"].is_null() {
            req["filter"] = c["filter"].clone();
        }
        let r = e.handle(&req);
        assert_eq!(r["profile"], "genome_topics_v1", "{r}");
        let got: Vec<i64> = r["hits"].as_array().unwrap().iter().map(|h| h["verse_id"].as_i64().unwrap()).collect();
        let want: Vec<i64> = c["ids"].as_array().unwrap().iter().map(|v| v.as_i64().unwrap()).collect();
        if got != want {
            bad.push(format!("verse {}: got {got:?} want {want:?}", c["verse_id"]));
        }
        // the plain genome ranking stays reachable
        req["topics"] = json!(false);
        let plain = e.handle(&req);
        assert_eq!(plain["profile"], "genome_weighted_cosine_v1");
        let g: Vec<i64> = plain["hits"].as_array().unwrap().iter().map(|h| h["verse_id"].as_i64().unwrap()).collect();
        let gw: Vec<i64> = c["genome_only"].as_array().unwrap().iter().map(|v| v.as_i64().unwrap()).collect();
        assert_eq!(g, gw);
    }
    assert!(bad.is_empty(), "{}", bad.join("\n"));
}

#[test]
fn configuration_identity_matches_python() {
    let g = read("test/golden/config_identity.json");
    let ids: Vec<i64> = g["filter_ids"].as_array().unwrap().iter().map(|v| v.as_i64().unwrap()).collect();
    let fsha = identity::filter_hash(Some(&ids));
    assert_eq!(fsha.as_deref(), g["filter_sha256"].as_str());
    let mut parts = g["parts"].as_object().unwrap().clone();
    parts.insert("filter_sha256".into(), json!(fsha));
    let parts = Value::Object(parts);
    assert_eq!(identity::configuration_id(&parts, "semantic"), g["configuration_id_semantic"].as_str().unwrap());
    assert_eq!(identity::configuration_id(&parts, "phrase"), g["configuration_id_phrase"].as_str().unwrap());
    let semantic = identity::configuration_id(&parts, "semantic");
    assert_eq!(identity::cache_key("What is faith?", &semantic, "semantic", None, 20, "english"), g["cache_key"].as_str().unwrap());
}

#[test]
fn requests_route_and_fail_cleanly() {
    let Some(e) = open() else { return };
    let ok = |v: &Value| assert!(v.get("error").is_none(), "{v}");

    // semantic search equals the Python reference for Compass
    let golden = read("test/golden/fusion_engine_int8_matmul.json");
    let q = golden["queries"].as_array().unwrap().iter().find(|q| q["text"] == "What is faith?").unwrap();
    let r = e.handle(&json!({"op": "semantic", "query": "What is faith?", "top_k": 20, "request_id": 1}));
    ok(&r);
    let got: Vec<i64> = r["hits"].as_array().unwrap().iter().map(|h| h["verse_id"].as_i64().unwrap()).collect();
    let want: Vec<i64> = q["profiles"]["compass"]["ids"].as_array().unwrap().iter().map(|v| v.as_i64().unwrap()).collect();
    assert_eq!(got, want);
    assert_eq!(r["profile"], "compass");
    assert_eq!(r["configuration_id"].as_str().unwrap().len(), 64);

    // references short-circuit; unknown text falls through to semantic
    let r = e.handle(&json!({"op": "search", "query": "John 3:16"}));
    assert_eq!(r["mode"], "reference");
    assert_eq!(r["reference"]["first_verse_id"], 26137);
    let r = e.handle(&json!({"op": "search", "query": "How do I overcome fear?"}));
    assert_eq!(r["mode"], "semantic");

    // person question: interpretation chip and the right person's verses
    let r = e.handle(&json!({"op": "search", "query": "Who is Captain Moroni?"}));
    ok(&r);
    assert_eq!(r["interpretation"]["person"]["status"], "single");
    assert_eq!(r["interpretation"]["person"]["people"][0]["entity_id"], "person:moroni_captain");
    let hits = r["hits"].as_array().unwrap();
    assert!(hits.iter().take(10).filter(|h| (33578..=35552).contains(&h["verse_id"].as_i64().unwrap())).count() >= 8, "Alma range: {hits:?}");

    // filter keeps results inside the ranges, and its hash changes the identity
    let all = e.handle(&json!({"op": "semantic", "query": "faith"}));
    let filtered = e.handle(&json!({"op": "semantic", "query": "faith", "filter": [[26137, 26200]], "top_k": 5}));
    ok(&filtered);
    assert!(filtered["hits"].as_array().unwrap().iter().all(|h| (26137..=26200).contains(&h["verse_id"].as_i64().unwrap())));
    assert_ne!(all["configuration_id"], filtered["configuration_id"]);
    let none = e.handle(&json!({"op": "semantic", "query": "faith", "filter": [[1, 0]]}));
    assert_eq!(none["hits"].as_array().unwrap().len(), 0);

    // phrase and similar
    let r = e.handle(&json!({"op": "phrase", "phrase": "the Lord is my shepherd"}));
    assert!(r["total"].as_u64().unwrap() >= 1);
    let r = e.handle(&json!({"op": "similar", "verse_id": 26137, "top_k": 5}));
    assert_eq!(r["hits"].as_array().unwrap().len(), 5);

    // typed errors
    assert_eq!(e.handle(&json!({"op": "semantic", "query": "   "}))["error"]["code"], "invalid_input");
    assert_eq!(e.handle(&json!({"op": "phrase", "phrase": "faith", "language": "klingon"}))["error"]["code"], "unsupported_language");
    assert_eq!(e.handle(&json!({"op": "similar", "verse_id": -3}))["error"]["code"], "unknown_verse");
    assert_eq!(e.handle(&json!({"op": "nope"}))["error"]["code"], "invalid_input");
    assert_eq!(e.handle(&json!({"op": "semantic", "query": "faith", "profile": "ghost"}))["error"]["code"], "invalid_input");
    let long = "faith ".repeat(600);
    assert_eq!(e.handle(&json!({"op": "semantic", "query": long}))["error"]["code"], "invalid_input");
    let info = e.handle(&json!({"op": "info"}));
    assert_eq!(info["colbert_pack"], true);
    assert_eq!(info["verses"], 41995);
}

#[test]
fn a_cancelled_request_stops() {
    let Some(e) = open() else { return };
    let e = std::sync::Arc::new(e);
    let e2 = e.clone();
    // cancel before the request registers is a no-op; cancel from another thread while it runs is honoured at a checkpoint
    let t = std::thread::spawn(move || e2.handle(&json!({"op": "semantic", "query": "What does the Bible teach about forgiveness?", "request_id": 77})));
    for _ in 0..2000 {
        e.cancel(77);
        if t.is_finished() {
            break;
        }
        std::thread::sleep(std::time::Duration::from_millis(1));
    }
    let r = t.join().unwrap();
    // either it was cancelled at a checkpoint or it finished first; both are valid, an error must be the typed one
    if let Some(err) = r.get("error") {
        assert_eq!(err["code"], "cancelled");
    }
}
