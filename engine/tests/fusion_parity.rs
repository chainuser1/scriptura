//! Gate E1: native fusion versus the Python deployment-shaped reference (test/golden/fusion_engine_int8_matmul.json):
//! same INT8 encoder, FP16 head, stored indexes and ColBERT pack, every named profile, top-20 verse IDs equal.

use scripture_engine::{encoder::Encoder, search::{Index, Weights}, tokenizer::QueryTokenizer};
use std::path::PathBuf;

fn root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).parent().unwrap().to_path_buf()
}

#[test]
fn every_profile_matches_the_python_reference() {
    let ext = root().join(".artifact-staging/import-application-v1/extracted");
    let model = root().join("generated-artifacts/onnx-int8/bge_m3_multi_int8_matmul.onnx");
    let pack = root().join("generated-artifacts/colbert-pack-v1");
    let retrieval = ext.join("scripture-retrieval-english-v1");
    let head = ext.join("scripture-genome-question-hidden4096-optimized/head_fp16.npz");
    if !model.exists() || !pack.join("shard-0000.vec.npy").exists() || !retrieval.exists() {
        eprintln!("skipped: model, pack or retrieval index not present");
        return;
    }
    let golden: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(root().join("test/golden/fusion_engine_int8_matmul.json")).unwrap()).unwrap();
    let tok = QueryTokenizer::from_file(ext.join("bge-m3-pinned/tokenizer.json")).unwrap();
    let mut enc = Encoder::open(&model, 1).unwrap();
    let t0 = std::time::Instant::now();
    let index = Index::open(&retrieval, &head, Some(&pack)).unwrap();
    println!("index opened in {:.1}s", t0.elapsed().as_secs_f32());

    let profiles = golden["meta"]["profiles"].as_object().unwrap();
    let mut bad = Vec::new();
    let mut totals: Vec<f64> = Vec::new();
    for q in golden["queries"].as_array().unwrap() {
        let text = q["text"].as_str().unwrap();
        let te = std::time::Instant::now();
        let encoded = enc.encode(&tok.encode(text).unwrap()).unwrap();
        let encode_ms = te.elapsed().as_secs_f64() * 1000.0;
        let t = std::time::Instant::now();
        for (name, w) in profiles {
            let w: Vec<f64> = w.as_array().unwrap().iter().map(|v| v.as_f64().unwrap()).collect();
            let weights = Weights { echo: w[0], spark: w[1], thread: w[2], root: w[3] };
            let ts = std::time::Instant::now();
            let out = index.search(&encoded, &weights, 20, None, &|| false).unwrap();
            if name == "compass" {
                totals.push(encode_ms + ts.elapsed().as_secs_f64() * 1000.0);
            }
            let want = &q["profiles"][name];
            let want_ids: Vec<i64> = want["ids"].as_array().unwrap().iter().map(|v| v.as_i64().unwrap()).collect();
            let want_scores: Vec<f64> = want["scores"].as_array().unwrap().iter().map(|v| v.as_f64().unwrap()).collect();
            let got_ids: Vec<i64> = out.hits.iter().map(|h| h.verse_id).collect();
            let max_ds = out.hits.iter().zip(&want_scores).map(|(h, s)| (h.score - s).abs()).fold(0f64, f64::max);
            if got_ids != want_ids || max_ds > 1e-3 || out.candidates != q["candidates"].as_u64().unwrap() as usize {
                bad.push(format!("{text:?} / {name}: ids_equal={} max|dscore|={max_ds:.2e} candidates {} vs {}",
                    got_ids == want_ids, out.candidates, q["candidates"]));
            }
        }
        println!("{text:?}: {} profiles in {:.0} ms", profiles.len(), t.elapsed().as_secs_f64() * 1000.0);
    }
    totals.sort_by(|a, b| a.partial_cmp(b).unwrap());
    println!("end-to-end Compass (encode + search), warm: median {:.0} ms, max {:.0} ms over {} queries",
        totals[totals.len() / 2], totals[totals.len() - 1], totals.len());
    assert!(bad.is_empty(), "{} mismatches:\n{}", bad.len(), bad.join("\n"));
}
