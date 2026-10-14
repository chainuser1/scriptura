//! Gate E1: phrase search, reference parsing and similar verses against the Python reference goldens
//! (test/golden/engine_capabilities.json), plus a full catalog round trip: every verse of every served language,
//! written as "<book> <chapter>:<verse>" in that language, parses back to its own verse ID.

use rusqlite::{Connection, OpenFlags};
use scripture_engine::{
    phrase::PhraseIndex,
    reference::{Catalog, Reference},
    search::Index,
};
use std::path::PathBuf;

fn root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).parent().unwrap().to_path_buf()
}

fn golden() -> serde_json::Value {
    serde_json::from_str(&std::fs::read_to_string(root().join("test/golden/engine_capabilities.json")).unwrap()).unwrap()
}

fn release() -> Option<PathBuf> {
    let d = root().join("generated-artifacts/release");
    d.join("catalog.db").exists().then_some(d)
}

#[test]
fn phrase_search_matches_reference() {
    let Some(rel) = release() else { return eprintln!("skipped: release not built") };
    let idx = PhraseIndex::open(rel.join("phrase-index.db")).unwrap();
    let g = golden();
    for (key, lang) in [("phrase", "english"), ("phrase_es", "spanish")] {
        for (phrase, want) in g[key].as_object().unwrap() {
            let r = idx.search(phrase, lang, 20, None).unwrap();
            let ids: Vec<i64> = want["verse_ids"].as_array().unwrap().iter().map(|v| v.as_i64().unwrap()).collect();
            assert_eq!(r.verse_ids, ids, "{phrase}");
            assert_eq!(r.total as u64, want["total"].as_u64().unwrap(), "{phrase}");
            assert_eq!(r.truncated, want["truncated"].as_bool().unwrap(), "{phrase}");
        }
    }
    let a = idx.search("Lord  IS my   SHEPHERD", "english", 20, None).unwrap();
    let b = idx.search("Lord is my shepherd", "english", 20, None).unwrap();
    assert!(a.total > 0 && a.verse_ids == b.verse_ids, "case and spacing are ignored");
    assert_eq!(idx.search("shepherd my is Lord", "english", 20, None).unwrap().total, 0);
    assert_eq!(idx.search("", "english", 20, None).unwrap_err().0, "invalid_input");
    assert_eq!(idx.search("?!...", "english", 20, None).unwrap_err().0, "invalid_input");
    assert_eq!(idx.search("faith", "klingon", 20, None).unwrap_err().0, "unsupported_language");
    assert_eq!(idx.search("faith", "french", 20, None).unwrap_err().0, "unsupported_language");
}

#[test]
fn reference_parser_matches_reference_and_round_trips() {
    let Some(rel) = release() else { return eprintln!("skipped: release not built") };
    let cat = Catalog::open(rel.join("catalog.db")).unwrap();
    let g = golden();
    for (key, want) in g["reference"].as_object().unwrap() {
        let (lang, text) = key.split_once('|').unwrap();
        let got = serde_json::to_value(cat.parse(text, lang)).unwrap();
        for (k, v) in got.as_object().unwrap() {
            assert_eq!(&want[k], v, "{key}: field {k}");
        }
    }
    let p = |t: &str, l: &str| cat.parse(t, l);
    assert!(matches!(p("Jn3:16", "english"), Reference::NotAReference));
    assert!(matches!(p("what is faith", "english"), Reference::NotAReference));
    assert!(matches!(p("", "english"), Reference::NotAReference));
    assert!(matches!(p("John 22", "english"), Reference::OutOfRange { .. }));

    let content = Connection::open_with_flags(rel.join("content.db"), OpenFlags::SQLITE_OPEN_READ_ONLY).unwrap();
    let cat_db = Connection::open_with_flags(rel.join("catalog.db"), OpenFlags::SQLITE_OPEN_READ_ONLY).unwrap();
    let chapters: Vec<(i64, i64, i64)> = cat_db
        .prepare("SELECT book_id, chapter, first_verse_id FROM chapters ORDER BY first_verse_id")
        .unwrap()
        .query_map([], |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)))
        .unwrap()
        .map(Result::unwrap)
        .collect();
    for lang in &cat.languages {
        let names: std::collections::HashMap<i64, String> = cat_db
            .prepare(&format!("SELECT book_id, name FROM book_names_{lang}"))
            .unwrap()
            .query_map([], |r| Ok((r.get(0)?, r.get(1)?)))
            .unwrap()
            .map(Result::unwrap)
            .collect();
        let ids: Vec<i64> = content
            .prepare(&format!("SELECT verse_id FROM text_{lang} ORDER BY verse_id"))
            .unwrap()
            .query_map([], |r| r.get(0))
            .unwrap()
            .map(Result::unwrap)
            .collect();
        let mut bad = Vec::new();
        for vid in &ids {
            let i = chapters.partition_point(|c| c.2 <= *vid) - 1;
            let (bid, ch, lo) = chapters[i];
            let reference = format!("{} {}:{}", names[&bid], ch, vid - lo + 1);
            match cat.parse(&reference, lang) {
                Reference::Ok(r) if r.kind == "verse" && r.first_verse_id == *vid => {}
                other => bad.push((*vid, reference, format!("{other:?}"))),
            }
        }
        assert!(bad.is_empty(), "{lang}: {} failures, first {:?}", bad.len(), &bad[..bad.len().min(3)]);
        println!("round trip {lang}: {}/{}", ids.len(), ids.len());
    }
}

#[test]
fn similar_verses_match_reference() {
    let ext = root().join(".artifact-staging/import-application-v1/extracted");
    let retrieval = ext.join("scripture-retrieval-english-v1");
    let head = ext.join("scripture-genome-question-hidden4096-optimized/head_fp16.npz");
    if !retrieval.exists() {
        return eprintln!("skipped: retrieval bundle not present");
    }
    let index = Index::open(&retrieval, &head, None).unwrap();
    for (vid, want) in golden()["similar"].as_object().unwrap() {
        let v: i64 = vid.parse().unwrap();
        let got: Vec<i64> = index.similar(v, 10, None).unwrap().iter().map(|h| h.verse_id).collect();
        let want: Vec<i64> = want.as_array().unwrap().iter().map(|x| x.as_i64().unwrap()).collect();
        assert_eq!(got, want, "similar to {v}");
    }
    assert!(index.similar(-5, 10, None).is_err());
    let allowed = index.mask_from_ranges(&[(26137, 26137), (26100, 26110)]);
    let s = index.similar(26137, 5, Some(&allowed)).unwrap();
    assert!(s.iter().all(|h| (26100..=26110).contains(&h.verse_id)) && !s.iter().any(|h| h.verse_id == 26137));
}
