//! Phrase search over the FTS5 phrase index (contract: tool/phrase_search.py). The whole input is ONE phrase of
//! consecutive words; operators are never interpreted; text and query are NFC; accents are preserved; results are
//! in canonical verse order with the total match count.

use rusqlite::{Connection, OpenFlags};
use std::collections::HashSet;
use std::path::Path;
use std::sync::Mutex;
use unicode_normalization::UnicodeNormalization;

const LANGS: [&str; 8] = ["english", "spanish", "tagalog", "cebuano", "greek", "french", "german", "hebrew"];

#[derive(Debug)]
pub struct PhraseResult {
    pub verse_ids: Vec<i64>,
    pub total: usize,
    pub truncated: bool,
}

pub struct PhraseIndex {
    conn: Mutex<Connection>, // a SQLite connection is Send but not Sync
    languages: HashSet<String>,
}

fn to_match(phrase: &str) -> Result<String, (&'static str, String)> {
    let p: String = phrase.nfc().collect::<String>().trim().to_string();
    if p.is_empty() {
        return Err(("invalid_input", "empty phrase".into()));
    }
    if !p.chars().any(|c| c.is_alphanumeric() || c == '_') {
        return Err(("invalid_input", "phrase has no searchable words".into()));
    }
    Ok(format!("\"{}\"", p.replace('"', "\"\"")))
}

impl PhraseIndex {
    pub fn open(path: impl AsRef<Path>) -> Result<Self, String> {
        let conn = Connection::open_with_flags(path.as_ref(), OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_URI)
            .map_err(|e| format!("{}: {e}", path.as_ref().display()))?;
        let mut st = conn.prepare("SELECT name FROM sqlite_master WHERE type='table'").map_err(|e| e.to_string())?;
        let languages = st
            .query_map([], |r| r.get::<_, String>(0))
            .map_err(|e| e.to_string())?
            .filter_map(Result::ok)
            .filter_map(|n| n.strip_prefix("phrase_").map(str::to_string))
            .filter(|n| LANGS.contains(&n.as_str()))
            .collect();
        drop(st);
        Ok(Self { conn: Mutex::new(conn), languages })
    }

    pub fn languages(&self) -> Vec<String> {
        let mut v: Vec<String> = self.languages.iter().cloned().collect();
        v.sort();
        v
    }

    /// Errors are `(code, message)` with the codes of docs/SEARCH_SPEC.md.
    pub fn search(
        &self,
        phrase: &str,
        language: &str,
        top_k: usize,
        allowed: Option<&HashSet<i64>>,
    ) -> Result<PhraseResult, (&'static str, String)> {
        if !LANGS.contains(&language) {
            return Err(("unsupported_language", format!("unknown language {language:?}")));
        }
        let m = to_match(phrase)?;
        if !self.languages.contains(language) {
            return Err(("unsupported_language", format!("language {language:?} has no phrase index (not served)")));
        }
        // language is allow-listed above, so interpolating the table name is safe
        let sql = format!("SELECT rowid FROM phrase_{language} WHERE phrase_{language} MATCH ?1 ORDER BY rowid");
        let conn = self.conn.lock().map_err(|_| ("internal", "phrase index lock poisoned".to_string()))?;
        let mut st = conn.prepare(&sql).map_err(|e| ("internal", e.to_string()))?;
        let mut ids: Vec<i64> = st
            .query_map([&m], |r| r.get::<_, i64>(0))
            .map_err(|e| ("internal", e.to_string()))?
            .collect::<Result<_, _>>()
            .map_err(|e| ("internal", e.to_string()))?;
        if let Some(a) = allowed {
            ids.retain(|i| a.contains(i));
        }
        let total = ids.len();
        ids.truncate(top_k);
        Ok(PhraseResult { verse_ids: ids, total, truncated: total > top_k })
    }
}
