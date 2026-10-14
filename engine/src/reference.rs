//! Scripture reference parsing (contract: tool/reference_parser.py). Output is verse-ID ranges validated against the
//! catalog; text that is not a reference is reported as such, never guessed.

use regex::Regex;
use rusqlite::{Connection, OpenFlags};
use serde::Serialize;
use std::collections::HashMap;
use std::path::Path;
use unicode_normalization::char::is_combining_mark;
use unicode_normalization::UnicodeNormalization;

const LANGS: [&str; 8] = ["english", "spanish", "tagalog", "cebuano", "greek", "french", "german", "hebrew"];

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Candidate {
    pub book_id: i64,
    pub book: String,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
#[serde(tag = "status", rename_all = "snake_case")]
pub enum Reference {
    NotAReference,
    Ambiguous { candidates: Vec<Candidate> },
    OutOfRange { book_id: i64, book: String, kind: String, reason: String },
    Ok(Resolved),
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Resolved {
    pub matched_language: String,
    pub book_id: i64,
    pub book: String,
    pub kind: String,
    pub first_verse_id: i64,
    pub last_verse_id: i64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub chapter: Option<i64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub chapter_end: Option<i64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub verse: Option<i64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub verse_end: Option<i64>,
}

struct Book {
    name: String,
    first: i64,
    last: i64,
    chapters: i64,
}

pub struct Catalog {
    pub languages: Vec<String>,
    books: HashMap<i64, Book>,
    chapters: HashMap<(i64, i64), (i64, i64)>,
    aliases: HashMap<String, HashMap<String, i64>>,
    patterns: Vec<(&'static str, Regex)>,
}

fn fold(s: &str) -> String {
    let n: String = s.nfc().collect::<String>().to_lowercase().replace('—', "--").replace('’', "'");
    n.split_whitespace().collect::<Vec<_>>().join(" ")
}

fn strip_marks(s: &str) -> String {
    s.nfd().filter(|c| !is_combining_mark(*c)).nfc().collect()
}

fn alias_keys(text: &str) -> Vec<String> {
    let base = fold(text).replace('.', "");
    let base = base.split_whitespace().collect::<Vec<_>>().join(" ");
    let mut third = base.clone();
    // "1 john" -> "1john"
    let b: Vec<char> = base.chars().collect();
    if b.len() > 1 && b[0].is_ascii_digit() && b[1].is_whitespace() {
        third = format!("{}{}", b[0], base[b[0].len_utf8()..].trim_start());
    }
    let mut out: Vec<String> = Vec::new();
    for k in [base.clone(), strip_marks(&base), third] {
        if !k.is_empty() && !out.contains(&k) {
            out.push(k);
        }
    }
    out
}

impl Catalog {
    pub fn open(path: impl AsRef<Path>) -> Result<Self, String> {
        let c = Connection::open_with_flags(path.as_ref(), OpenFlags::SQLITE_OPEN_READ_ONLY).map_err(|e| e.to_string())?;
        let served: String =
            c.query_row("SELECT value FROM catalog_meta WHERE key = 'served_languages'", [], |r| r.get(0)).map_err(|e| e.to_string())?;
        let languages: Vec<String> = served.split(',').filter(|l| !l.is_empty()).map(str::to_string).collect();
        let mut books = HashMap::new();
        let mut st = c
            .prepare("SELECT book_id, canonical_name, first_verse_id, last_verse_id, chapter_count FROM books")
            .map_err(|e| e.to_string())?;
        for r in st
            .query_map([], |r| Ok((r.get::<_, i64>(0)?, Book { name: r.get(1)?, first: r.get(2)?, last: r.get(3)?, chapters: r.get(4)? })))
            .map_err(|e| e.to_string())?
        {
            let (id, b) = r.map_err(|e| e.to_string())?;
            books.insert(id, b);
        }
        let mut chapters = HashMap::new();
        let mut st = c.prepare("SELECT book_id, chapter, first_verse_id, last_verse_id FROM chapters").map_err(|e| e.to_string())?;
        for r in st
            .query_map([], |r| Ok(((r.get::<_, i64>(0)?, r.get::<_, i64>(1)?), (r.get::<_, i64>(2)?, r.get::<_, i64>(3)?))))
            .map_err(|e| e.to_string())?
        {
            let (k, v) = r.map_err(|e| e.to_string())?;
            chapters.insert(k, v);
        }
        let mut aliases = HashMap::new();
        for lang in &languages {
            if !LANGS.contains(&lang.as_str()) {
                return Err(format!("unexpected language {lang:?} in catalog"));
            }
            let mut m = HashMap::new();
            let mut st = c.prepare(&format!("SELECT alias, book_id FROM book_aliases_{lang}")).map_err(|e| e.to_string())?;
            for r in st.query_map([], |r| Ok((r.get::<_, String>(0)?, r.get::<_, i64>(1)?))).map_err(|e| e.to_string())? {
                let (a, b) = r.map_err(|e| e.to_string())?;
                m.insert(a, b);
            }
            aliases.insert(lang.clone(), m);
        }
        Ok(Self { languages, books, chapters, aliases, patterns: Self::patterns() })
    }

    fn patterns() -> Vec<(&'static str, Regex)> {
        let sep = r"\s*[:.,]\s*";
        let dash = r"\s*[-–—]\s*";
        let re = |s: String| Regex::new(&s).unwrap();
        vec![
            ("range_x", re(format!(r"^(?P<c1>[0-9]+){sep}(?P<v1>[0-9]+){dash}(?P<c2>[0-9]+){sep}(?P<v2>[0-9]+)$"))),
            ("range", re(format!(r"^(?P<c1>[0-9]+){sep}(?P<v1>[0-9]+){dash}(?P<v2>[0-9]+)$"))),
            ("verse", re(format!(r"^(?P<c1>[0-9]+){sep}(?P<v1>[0-9]+)$"))),
            ("chapters", re(format!(r"^(?P<c1>[0-9]+){dash}(?P<c2>[0-9]+)$"))),
            ("chapter", re(r"^(?P<c1>[0-9]+)$".to_string())),
        ]
    }

    /// (tier language, book ids): active language first, then English, then every other served language together.
    fn lookup(&self, text: &str, language: &str) -> (Option<String>, Vec<i64>) {
        let mut order: Vec<String> = vec![language.to_string()];
        if language != "english" {
            order.push("english".into());
        }
        let others: Vec<String> = self.languages.iter().filter(|l| !order.contains(l)).cloned().collect();
        let mut tiers: Vec<Vec<String>> = order.iter().filter(|l| self.aliases.contains_key(*l)).map(|l| vec![l.clone()]).collect();
        if !others.is_empty() {
            tiers.push(others);
        }
        let keys = alias_keys(text);
        for tier in tiers {
            let mut hits: Vec<i64> = Vec::new();
            for lang in &tier {
                for k in &keys {
                    if let Some(&b) = self.aliases.get(lang).and_then(|m| m.get(k)) {
                        if !hits.contains(&b) {
                            hits.push(b);
                        }
                        break;
                    }
                }
            }
            if !hits.is_empty() {
                return (Some(tier[0].clone()), hits);
            }
        }
        (None, Vec::new())
    }

    pub fn parse(&self, text: &str, language: &str) -> Reference {
        let s = fold(text);
        if s.is_empty() {
            return Reference::NotAReference;
        }
        let tokens: Vec<&str> = s.split(' ').collect();
        for i in (1..tokens.len()).rev() {
            let (prefix, suffix) = (tokens[..i].join(" "), tokens[i..].join(" "));
            for (kind, pat) in &self.patterns {
                let Some(m) = pat.captures(&suffix) else { continue };
                let (tier, books) = self.lookup(&prefix, language);
                if books.is_empty() {
                    break;
                }
                let n = |k: &str| m.name(k).and_then(|x| x.as_str().parse::<i64>().ok());
                return self.resolve(tier.unwrap(), books, kind, n("c1"), n("v1"), n("c2"), n("v2"));
            }
        }
        let (tier, books) = self.lookup(&s, language);
        if !books.is_empty() {
            return self.resolve(tier.unwrap(), books, "book", None, None, None, None);
        }
        Reference::NotAReference
    }

    #[allow(clippy::too_many_arguments)]
    fn resolve(&self, tier: String, books: Vec<i64>, kind: &str, c1: Option<i64>, v1: Option<i64>, c2: Option<i64>, v2: Option<i64>) -> Reference {
        if books.len() > 1 {
            return Reference::Ambiguous {
                candidates: books.iter().map(|&b| Candidate { book_id: b, book: self.books[&b].name.clone() }).collect(),
            };
        }
        let bid = books[0];
        let book = &self.books[&bid];
        let bad = |reason: String| Reference::OutOfRange { book_id: bid, book: book.name.clone(), kind: kind.to_string(), reason };
        let mut out = Resolved {
            matched_language: tier,
            book_id: bid,
            book: book.name.clone(),
            kind: kind.to_string(),
            first_verse_id: book.first,
            last_verse_id: book.last,
            chapter: None,
            chapter_end: None,
            verse: None,
            verse_end: None,
        };
        if kind == "book" {
            return Reference::Ok(out);
        }
        let c1n = c1.unwrap();
        let Some(&ch1) = self.chapters.get(&(bid, c1n)) else {
            return bad(format!("{} has {} chapters, not {}", book.name, book.chapters, c1n));
        };
        if kind == "chapter" {
            out.chapter = Some(c1n);
            out.first_verse_id = ch1.0;
            out.last_verse_id = ch1.1;
            return Reference::Ok(out);
        }
        if kind == "chapters" {
            let c2n = c2.unwrap();
            return match self.chapters.get(&(bid, c2n)) {
                Some(&ch2) if c2n >= c1n => {
                    out.chapter = Some(c1n);
                    out.chapter_end = Some(c2n);
                    out.first_verse_id = ch1.0;
                    out.last_verse_id = ch2.1;
                    Reference::Ok(out)
                }
                _ => bad(format!("chapter range {c1n}-{c2n} is not valid in {}", book.name)),
            };
        }
        let v1n = v1.unwrap();
        let n1 = ch1.1 - ch1.0 + 1;
        if !(1..=n1).contains(&v1n) {
            return bad(format!("{} {} has {} verses, not {}", book.name, c1n, n1, v1n));
        }
        let first = ch1.0 + v1n - 1;
        if kind == "verse" {
            out.chapter = Some(c1n);
            out.verse = Some(v1n);
            out.first_verse_id = first;
            out.last_verse_id = first;
            return Reference::Ok(out);
        }
        let c2n = c2.unwrap_or(c1n);
        let Some(&ch2) = self.chapters.get(&(bid, c2n)) else {
            return bad(format!("{} has {} chapters, not {}", book.name, book.chapters, c2n));
        };
        let v2n = v2.unwrap();
        let n2 = ch2.1 - ch2.0 + 1;
        if !(1..=n2).contains(&v2n) {
            return bad(format!("{} {} has {} verses, not {}", book.name, c2n, n2, v2n));
        }
        let last = ch2.0 + v2n - 1;
        if last < first {
            return bad("range ends before it starts".into());
        }
        out.chapter = Some(c1n);
        out.verse = Some(v1n);
        out.chapter_end = Some(c2n);
        out.verse_end = Some(v2n);
        out.first_verse_id = first;
        out.last_verse_id = last;
        Reference::Ok(out)
    }
}
