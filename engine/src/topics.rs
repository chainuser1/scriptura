//! Topic lane for similar verses (contract: tool/similar_verses.py `similar_with_topics`).
//!
//! Each verse has an L2-normalised tf-idf vector over topic numbers, so the dot product of two verses is their topic
//! cosine. The lane is fused with the genome cosine by z-score over the union of each lane's top candidates.

use rusqlite::{Connection, OpenFlags};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::path::Path;

pub struct TopicIndex {
    by_verse: HashMap<i64, Vec<(u32, f32)>>,
    postings: HashMap<u32, Vec<(i64, f32)>>,
    pub weight: f64,
    pub lane_k: usize,
    pub sha256: String,
}

impl TopicIndex {
    pub fn open(path: impl AsRef<Path>) -> Result<Self, String> {
        let path = path.as_ref();
        let bytes = std::fs::read(path).map_err(|e| format!("{}: {e}", path.display()))?;
        let sha256 = format!("{:x}", Sha256::digest(&bytes));
        drop(bytes);
        let c = Connection::open_with_flags(path, OpenFlags::SQLITE_OPEN_READ_ONLY).map_err(|e| e.to_string())?;
        let meta = |k: &str| -> Option<String> { c.query_row("SELECT value FROM meta WHERE key = ?1", [k], |r| r.get(0)).ok() };
        let weight = meta("weight").and_then(|s| s.parse().ok()).unwrap_or(0.5);
        let lane_k = meta("lane_k").and_then(|s| s.parse().ok()).unwrap_or(200);
        let mut by_verse: HashMap<i64, Vec<(u32, f32)>> = HashMap::new();
        let mut postings: HashMap<u32, Vec<(i64, f32)>> = HashMap::new();
        let mut st = c.prepare("SELECT topic, verse_id, w FROM posting").map_err(|e| e.to_string())?;
        let rows = st
            .query_map([], |r| Ok((r.get::<_, i64>(0)? as u32, r.get::<_, i64>(1)?, r.get::<_, f64>(2)? as f32)))
            .map_err(|e| e.to_string())?;
        for r in rows {
            let (t, v, w) = r.map_err(|e| e.to_string())?;
            by_verse.entry(v).or_default().push((t, w));
            postings.entry(t).or_default().push((v, w));
        }
        Ok(Self { by_verse, postings, weight, lane_k, sha256 })
    }

    /// The topic vector of a verse (empty when it has none).
    pub fn vector_of(&self, verse: i64) -> &[(u32, f32)] {
        self.by_verse.get(&verse).map(Vec::as_slice).unwrap_or(&[])
    }

    /// The verses carrying a topic, with their weights (empty for an unknown topic).
    pub fn postings_of(&self, topic: u32) -> &[(i64, f32)] {
        self.postings.get(&topic).map(Vec::as_slice).unwrap_or(&[])
    }

    /// Topic cosine of `verse_id` against every verse that shares a topic with it (the source itself excluded).
    pub fn scores(&self, verse_id: i64) -> HashMap<i64, f64> {
        let mut out: HashMap<i64, f64> = HashMap::new();
        if let Some(ts) = self.by_verse.get(&verse_id) {
            for &(t, w) in ts {
                for &(u, wu) in &self.postings[&t] {
                    if u != verse_id {
                        *out.entry(u).or_insert(0.0) += f64::from(w) * f64::from(wu);
                    }
                }
            }
        }
        out
    }
}
