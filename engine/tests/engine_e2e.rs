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

fn minimal_cfg_json() -> Value {
    json!({
        "retrieval_dir": "x",
        "head_npz": "x",
        "encoder_model": "x",
        "tokenizer_json": "x",
        "profiles": {"p": [0.0, 0.0, 0.0, 0.0]},
        "default_profile": "p",
        "fallback_without_thread": "p",
    })
}

#[test]
fn focus_family_absent_defaults_to_none_and_apollos_round_trips() {
    let absent = serde_json::from_value::<Config>(minimal_cfg_json()).unwrap();
    assert_eq!(absent.focus_family, None);

    let mut with_family = minimal_cfg_json();
    with_family["focus_family"] = json!("apollos");
    let cfg = serde_json::from_value::<Config>(with_family).unwrap();
    assert_eq!(cfg.focus_family, Some("apollos".to_string()));
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

#[test]
fn trails_match_python_goldens() {
    let Some(e) = open() else { return };
    let g = read("test/golden/trails.json");
    let mut bad = Vec::new();
    for (i, c) in g["next"].as_array().unwrap().iter().enumerate() {
        let got = e.handle(&c["request"]);
        assert!(got.get("error").is_none(), "case {i}: {got}");
        let ids = |v: &Value| -> Vec<i64> { v["hits"].as_array().unwrap().iter().map(|h| h["verse_id"].as_i64().unwrap()).collect() };
        if ids(&got) != ids(&c["response"]) {
            bad.push(format!("case {i}: got {:?} want {:?}", ids(&got), ids(&c["response"])));
            continue;
        }
        for (a, b) in got["hits"].as_array().unwrap().iter().zip(c["response"]["hits"].as_array().unwrap()) {
            let (x, y) = (a["score"].as_f64().unwrap(), b["score"].as_f64().unwrap());
            assert!((x - y).abs() < 1e-5, "case {i} score {x} vs {y}");
        }
        assert_eq!(got["widened"], c["response"]["widened"], "case {i} widened");
        let fw: Vec<f64> = got["family_weights"].as_array().unwrap().iter().map(|v| v.as_f64().unwrap()).collect();
        let want: Vec<f64> = c["response"]["family_weights"].as_array().unwrap().iter().map(|v| v.as_f64().unwrap()).collect();
        assert!(fw.iter().zip(&want).all(|(a, b)| (a - b).abs() < 1e-6), "case {i} family weights");
    }
    assert!(bad.is_empty(), "{}", bad.join("\n"));
    for c in g["explain"].as_array().unwrap() {
        let got = e.handle(&c["request"]);
        let fams = |v: &Value| -> Vec<(String, Vec<String>)> {
            v["families"].as_array().unwrap().iter().map(|f| (f["family"].as_str().unwrap().to_string(),
                f["genes"].as_array().unwrap().iter().map(|x| x["id"].as_str().unwrap().to_string()).collect())).collect()
        };
        assert_eq!(fams(&got), fams(&c["response"]), "explain {}", c["request"]);
        assert_eq!(got["mood_matches"], c["response"]["mood_matches"]);
    }
    let t = e.handle(&g["taste"]["request"]);
    assert_eq!(t["families"].as_array().unwrap().len(), g["taste"]["response"]["families"].as_array().unwrap().len());
    for (a, b) in t["families"].as_array().unwrap().iter().zip(g["taste"]["response"]["families"].as_array().unwrap()) {
        assert_eq!(a["family"], b["family"]);
    }
}

#[test]
fn trail_text_seed_filter_and_errors() {
    let Some(e) = open() else { return };
    let base = json!({"op": "trail_next", "k": 5, "step": 0, "seed": {"text": "How do I forgive?"}, "events": [], "recent": [],
                      "moods": [], "mood_strength": 0.5, "focus": 0.5, "filter": null});
    let r = e.handle(&base);
    assert!(r.get("error").is_none(), "{r}");
    assert_eq!(r["hits"].as_array().unwrap().len(), 5);
    // a tiny filter returns what exists and says it widened, never an error
    let mut tiny = base.clone();
    tiny["filter"] = json!([[41361, 41363]]);
    tiny["seed"] = json!({"verse_id": 26137});
    let r = e.handle(&tiny);
    assert!(r.get("error").is_none(), "{r}");
    assert!(r["hits"].as_array().unwrap().len() <= 3);
    // typed failures
    let mut bad = base.clone();
    bad["seed"] = json!({"verse_id": -1});
    assert_eq!(e.handle(&bad)["error"]["code"], "invalid_input");
    let mut nothing = base.clone();
    nothing["seed"] = json!({});
    assert_eq!(e.handle(&nothing)["error"]["code"], "invalid_input");
}

#[test]
fn trail_next_meets_the_desktop_speed_budget() {
    let Some(e) = open() else { return };
    let req = json!({"op": "trail_next", "k": 10, "step": 0, "seed": {"verse_id": 26137}, "events": [], "recent": [],
                     "moods": [], "mood_strength": 0.5, "focus": 0.5, "filter": null,
                     "volume_balance": 0.75}); // as the app ships (tool/volume_balance.py STRENGTH)
    e.handle(&req); // warm
    let mut ms: Vec<f64> = (0..30)
        .map(|_| {
            let t = std::time::Instant::now();
            let r = e.handle(&req);
            assert!(r.get("error").is_none(), "{r}");
            t.elapsed().as_secs_f64() * 1000.0
        })
        .collect();
    ms.sort_by(|a, b| a.partial_cmp(b).unwrap());
    eprintln!("trail_next median {:.1} ms, p90 {:.1} ms", ms[15], ms[27]);
    // the fastest quartile, so that tests running in parallel on a busy machine do not make this flaky
    assert!(ms[7] <= 50.0, "fast-quartile {:.1} ms exceeds the 50 ms desktop budget", ms[7]);
}

fn ids_of(v: &Value) -> Vec<i64> {
    v["hits"].as_array().unwrap().iter().map(|h| h["verse_id"].as_i64().unwrap()).collect()
}

/// The same verses in the same order, except that two verses whose reference scores differ by less than 5e-5 (float noise in
/// a z-scored fusion) may swap.
fn same_up_to_near_ties(got: &Value, want: &Value) -> bool {
    let want_hits = want["hits"].as_array().or_else(|| want.as_array()).unwrap();
    let w: Vec<i64> = want_hits.iter().map(|h| h["verse_id"].as_i64().unwrap()).collect();
    let score = |id: i64| want_hits.iter().find(|h| h["verse_id"].as_i64() == Some(id)).map(|h| h["score"].as_f64().unwrap());
    let g = ids_of(got);
    g.len() == w.len()
        && g.iter().zip(&w).all(|(a, b)| a == b || matches!((score(*a), score(*b)), (Some(x), Some(y)) if (x - y).abs() < 5e-5))
}

#[test]
fn volume_balance_matches_python_goldens() {
    let Some(e) = open() else { return };
    let g = read("test/golden/volume_balance.json");
    let mut bad = Vec::new();
    for key in ["similar", "trails"] {
        for (i, c) in g[key].as_array().unwrap().iter().enumerate() {
            let got = e.handle(&c["request"]);
            assert!(got.get("error").is_none(), "{key} case {i}: {got}");
            if !same_up_to_near_ties(&got, &c["response"]) {
                bad.push(format!("{key} case {i} ({}): got {:?}", c["scope"], ids_of(&got)));
            }
        }
    }
    assert!(bad.is_empty(), "{} differ:\n{}", bad.len(), bad.join("\n"));
}

#[test]
fn volume_balance_off_and_one_volume_are_today() {
    let Some(e) = open() else { return };
    let bom = json!([[31103, 37706]]); // the whole Book of Mormon: one volume
    let cases = [
        json!({"op": "similar", "verse_id": 34000, "top_k": 10}),
        json!({"op": "similar", "verse_id": 34000, "top_k": 10, "topics": false}),
        json!({"op": "semantic", "query": "How do I find peace when I am afraid?", "top_k": 10, "profile": "compass"}),
        json!({"op": "trail_next", "k": 10, "step": 0, "seed": {"verse_id": 34000}}),
    ];
    for base in cases {
        let today = e.handle(&base);
        assert!(today.get("error").is_none(), "{today}");
        let mut off = base.clone();
        off["volume_balance"] = json!(0.0);
        assert_eq!(e.handle(&off)["hits"], today["hits"], "strength 0 = today: {base}");
        assert_eq!(e.handle(&off)["configuration_id"], today["configuration_id"], "strength 0 keeps the id: {base}");
        let mut one = base.clone();
        one["filter"] = bom.clone();
        let mut one_on = one.clone();
        one_on["volume_balance"] = json!(0.75);
        assert_eq!(e.handle(&one_on)["hits"], e.handle(&one)["hits"], "one volume in scope = today: {base}");
    }
}

#[test]
fn volume_balance_changes_canon_search() {
    let Some(e) = open() else { return };
    let mut changed = 0;
    for q in ["How do I find peace when I am afraid?", "What is grace?", "faith, hope and charity", "Noah and the flood"] {
        let base = json!({"op": "semantic", "query": q, "top_k": 10, "profile": "compass"});
        let mut on = base.clone();
        on["volume_balance"] = json!(0.75);
        let (a, b) = (e.handle(&base), e.handle(&on));
        assert!(b.get("error").is_none(), "{b}");
        assert_ne!(a["configuration_id"], b["configuration_id"]);
        changed += (ids_of(&a) != ids_of(&b)) as usize;
    }
    assert!(changed >= 1, "volume balance should change at least one canon search");
}

#[test]
fn volume_balance_rejects_bad_strength() {
    let Some(e) = open() else { return };
    for bad in [json!(1.5), json!(-0.1), json!("x")] {
        let r = e.handle(&json!({"op": "similar", "verse_id": 34000, "volume_balance": bad}));
        assert_eq!(r["error"]["code"], "invalid_input", "{bad}");
    }
}
