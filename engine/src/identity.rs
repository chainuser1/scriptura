//! Configuration identity and cache keys (contract: tool/config_identity.py). The identity is the SHA-256 of a
//! canonical JSON (sorted keys, compact separators, UTF-8) of everything that can change a ranking.

use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use unicode_normalization::UnicodeNormalization;

pub const SCHEMA: i64 = 1;

pub fn sha256_text(s: &str) -> String {
    format!("{:x}", Sha256::digest(s.as_bytes()))
}

/// serde_json maps are ordered by key, so `to_string` is the canonical form.
pub fn canonical(v: &Value) -> String {
    serde_json::to_string(v).expect("json value serialises")
}

/// None = whole corpus; otherwise independent of order and duplicates.
pub fn filter_hash(ids: Option<&[i64]>) -> Option<String> {
    ids.map(|ids| {
        let mut v = ids.to_vec();
        v.sort_unstable();
        v.dedup();
        sha256_text(&v.iter().map(i64::to_string).collect::<Vec<_>>().join(","))
    })
}

/// `parts` is a JSON object (artifact identities, fusion, filter hash); `mode` is semantic, phrase, ...
pub fn configuration_id(parts: &Value, mode: &str) -> String {
    let mut body = parts.as_object().cloned().unwrap_or_default();
    body.insert("schema".into(), json!(SCHEMA));
    body.insert("mode".into(), json!(mode));
    sha256_text(&canonical(&Value::Object(body)))
}

pub fn cache_key(query: &str, config_id: &str, mode: &str, filter_sha: Option<&str>, top_k: usize, search_language: &str) -> String {
    let q: String = query.nfc().collect();
    sha256_text(&canonical(&json!({
        "q": q, "config": config_id, "mode": mode, "filter": filter_sha, "top_k": top_k, "search_language": search_language
    })))
}
