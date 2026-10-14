//! Gate E1: every golden case encodes to byte-identical IDs (test/golden/tokenizer_ids.json, made by the Python
//! reference). The pinned tokenizer.json is located through SCRIPTURE_TOKENIZER_JSON or the staging default.

use scripture_engine::tokenizer::QueryTokenizer;
use sha2::{Digest, Sha256};
use std::path::PathBuf;

fn root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).parent().unwrap().to_path_buf()
}

fn tokenizer_path() -> PathBuf {
    match std::env::var("SCRIPTURE_TOKENIZER_JSON") {
        Ok(p) => PathBuf::from(p),
        Err(_) => root().join(".artifact-staging/import-application-v1/extracted/bge-m3-pinned/tokenizer.json"),
    }
}

#[test]
fn golden_ids_are_identical() {
    let path = tokenizer_path();
    if !path.exists() {
        eprintln!("skipped: {} not present", path.display());
        return;
    }
    let golden: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(root().join("test/golden/tokenizer_ids.json")).unwrap()).unwrap();
    let want_sha = golden["meta"]["tokenizer_json_sha256"].as_str().unwrap();
    let got_sha = format!("{:x}", Sha256::digest(std::fs::read(&path).unwrap()));
    assert_eq!(got_sha, want_sha, "tokenizer.json is not the pinned file");

    let tok = QueryTokenizer::from_file(&path).unwrap();
    let cases = golden["cases"].as_array().unwrap();
    assert_eq!(cases.len(), 40);
    let mut bad = Vec::new();
    for c in cases {
        // the golden stores long inputs truncated for display; the hash and length identify the real input
        let shown = c["text"].as_str().unwrap();
        let len = c["text_len"].as_u64().unwrap() as usize;
        let full: String = if shown.chars().count() < len { "x".repeat(len) } else { shown.to_string() };
        assert_eq!(format!("{:x}", Sha256::digest(full.as_bytes())), c["text_sha256"].as_str().unwrap(), "input {:?}", shown);
        let text = full.as_str();
        let want: Vec<u32> = c["ids"].as_array().unwrap().iter().map(|v| v.as_u64().unwrap() as u32).collect();
        let got = tok.encode(text).unwrap();
        if got != want {
            bad.push(format!("{:?}: want {:?} got {:?}", text, &want[..want.len().min(12)], &got[..got.len().min(12)]));
        }
    }
    assert!(bad.is_empty(), "{} of {} cases differ:\n{}", bad.len(), cases.len(), bad.join("\n"));
}
