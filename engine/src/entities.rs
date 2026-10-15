//! Gated person linking (contract: tool/entity_linker.py, word lists shared in engine/data/entity_linker_words.json).
//! "Who is Captain Moroni?" -> person:moroni_captain. Generic people are recognised but never filter results.

use regex::Regex;
use rusqlite::{Connection, OpenFlags};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use std::path::Path;
use unicode_normalization::char::is_combining_mark;
use unicode_normalization::UnicodeNormalization;

const WORDS_JSON: &str = include_str!("../data/entity_linker_words.json");

#[derive(Deserialize)]
struct Words {
    stop: Vec<String>,
    title_only: Vec<String>,
    person_question: Vec<String>,
    #[serde(default)]
    place_question: Vec<String>,
    #[serde(default)]
    about_question: Vec<String>,
    qualifier_words: HashMap<String, Vec<String>>,
    dominance: f64,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Link {
    pub status: &'static str, // none | single | ambiguous | generic
    pub candidates: Vec<String>,
    pub filter: bool,
    pub alternatives: Vec<String>,
}

struct Person {
    name: String,
    qualifier: String,
    n: i64,
    name_tok: HashSet<String>,
    slug_tok: HashSet<String>,
    qual_tok: HashSet<String>,
    generic: bool,
}

pub struct PeopleIndex {
    people: Vec<(String, Person)>,
    verses: HashMap<String, Vec<i64>>,
    by_verse: HashMap<i64, Vec<String>>,
    stop: HashSet<String>,
    title_only: HashSet<String>,
    to_english: HashMap<String, String>,
    questions: Vec<Regex>,
    place_questions: Vec<Regex>,
    about_questions: Vec<Regex>,
    word: Regex,
    dominance: f64,
}

fn fold(s: &str) -> String {
    s.to_lowercase().nfd().filter(|c| !is_combining_mark(*c)).collect()
}

impl PeopleIndex {
    pub fn open(path: impl AsRef<Path>) -> Result<Self, String> {
        let w: Words = serde_json::from_str(WORDS_JSON).map_err(|e| e.to_string())?;
        let stop: HashSet<String> = w.stop.iter().map(|s| fold(s)).collect();
        let to_english = w
            .qualifier_words
            .iter()
            .flat_map(|(en, ws)| ws.iter().map(move |x| (x.clone(), en.clone())))
            .collect::<HashMap<_, _>>();
        let mut me = Self {
            people: Vec::new(),
            verses: HashMap::new(),
            by_verse: HashMap::new(),
            stop,
            title_only: w.title_only.into_iter().collect(),
            to_english,
            questions: w.person_question.iter().map(|p| Regex::new(p).map_err(|e| e.to_string())).collect::<Result<_, _>>()?,
            place_questions: w.place_question.iter().map(|p| Regex::new(p).map_err(|e| e.to_string())).collect::<Result<_, _>>()?,
            about_questions: w.about_question.iter().map(|p| Regex::new(p).map_err(|e| e.to_string())).collect::<Result<_, _>>()?,
            word: Regex::new(r"[\w']+").unwrap(),
            dominance: w.dominance,
        };
        let c = Connection::open_with_flags(path.as_ref(), OpenFlags::SQLITE_OPEN_READ_ONLY).map_err(|e| e.to_string())?;
        let mut st = c
            .prepare("SELECT entity_id, name, qualifier, description, verse_count, generic FROM people ORDER BY entity_id")
            .map_err(|e| e.to_string())?;
        let rows = st
            .query_map([], |r| {
                Ok((r.get::<_, String>(0)?, r.get::<_, String>(1)?, r.get::<_, String>(2)?, r.get::<_, String>(3)?, r.get::<_, i64>(4)?, r.get::<_, i64>(5)?))
            })
            .map_err(|e| e.to_string())?;
        for r in rows {
            let (id, name, qual, desc, n, generic) = r.map_err(|e| e.to_string())?;
            let name_tok: HashSet<String> = me.tokens(name.split(',').next().unwrap_or("")).into_iter().collect();
            let slug = id.split_once(':').map(|x| x.1).unwrap_or(&id).replace('_', " ");
            let slug_tok: HashSet<String> = me.tokens(&slug).into_iter().collect();
            let qual_tok: HashSet<String> = me.tokens(&format!("{qual} {desc}")).into_iter().filter(|t| !name_tok.contains(t)).collect();
            me.people.push((id, Person { name, qualifier: qual, n, name_tok, slug_tok, qual_tok, generic: generic != 0 }));
        }
        drop(st);
        let mut st = c.prepare("SELECT entity_id, verse_id FROM person_verses ORDER BY entity_id, verse_id").map_err(|e| e.to_string())?;
        for r in st.query_map([], |r| Ok((r.get::<_, String>(0)?, r.get::<_, i64>(1)?))).map_err(|e| e.to_string())? {
            let (id, v) = r.map_err(|e| e.to_string())?;
            me.by_verse.entry(v).or_default().push(id.clone());
            me.verses.entry(id).or_default().push(v);
        }
        drop(st);
        Ok(me)
    }

    fn tokens(&self, s: &str) -> Vec<String> {
        self.word.find_iter(&fold(s)).map(|m| m.as_str().to_string()).filter(|t| !self.stop.contains(t)).collect()
    }

    /// Entity kinds a question may be about: "who" -> people and groups, "where" -> places, "tell me about" -> all.
    fn question_kinds(&self, q: &str) -> Option<&'static [&'static str]> {
        let f = fold(q);
        let f = f.trim().trim_start_matches(['¿', '¡']);
        if self.questions.iter().any(|p| p.is_match(f)) {
            Some(&["person", "group"])
        } else if self.place_questions.iter().any(|p| p.is_match(f)) {
            Some(&["place"])
        } else if self.about_questions.iter().any(|p| p.is_match(f)) {
            Some(&["person", "group", "place"])
        } else {
            None
        }
    }

    /// Entities linked to a verse, by entity id.
    pub fn entities_of(&self, verse: i64) -> Vec<String> {
        self.by_verse.get(&verse).cloned().unwrap_or_default()
    }

    pub fn verses_of(&self, entity_id: &str) -> &[i64] {
        self.verses.get(entity_id).map(Vec::as_slice).unwrap_or(&[])
    }

    pub fn display(&self, entity_id: &str) -> Option<(&str, &str)> {
        self.people.iter().find(|(id, _)| id == entity_id).map(|(_, p)| (p.name.as_str(), p.qualifier.as_str()))
    }

    /// The user picked this person from an interpretation chip: no guessing, exactly this entity.
    pub fn forced(&self, entity_id: &str) -> Option<Link> {
        let (_, p) = self.people.iter().find(|(id, _)| id == entity_id)?;
        Some(Link { status: "single", candidates: vec![entity_id.to_string()], filter: !p.generic, alternatives: vec![] })
    }

    pub fn link(&self, query: &str) -> Link {
        let none = Link { status: "none", candidates: vec![], filter: false, alternatives: vec![] };
        let Some(kinds) = self.question_kinds(query) else {
            return none;
        };
        let q: HashSet<String> = self.tokens(query).into_iter().collect();
        let mut q_en = q.clone();
        q_en.extend(q.iter().filter_map(|t| self.to_english.get(t).cloned()));

        let subset = |a: &HashSet<String>| !a.is_empty() && a.iter().all(|t| q_en.contains(t));
        let title = |a: &HashSet<String>| a.iter().all(|t| self.title_only.contains(t));
        let mut found: Vec<usize> = (0..self.people.len())
            .filter(|&i| {
                let p = &self.people[i].1;
                let kind_ok = self.people[i].0.split(':').next().map_or(false, |k| kinds.contains(&k));
                kind_ok && ((subset(&p.name_tok) && !title(&p.name_tok)) || (subset(&p.slug_tok) && !title(&p.slug_tok)))
            })
            .collect();
        if found.is_empty() {
            return none;
        }
        let specificity = |i: usize| -> i64 {
            let p = &self.people[i].1;
            let sib: HashSet<&String> = found.iter().filter(|&&o| o != i).flat_map(|&o| self.people[o].1.slug_tok.iter()).collect();
            let rest: HashSet<&String> = q_en.iter().filter(|t| !p.name_tok.contains(*t)).collect();
            let a = rest.iter().filter(|t| p.slug_tok.contains(**t)).count() as i64;
            let b = rest.iter().filter(|t| p.qual_tok.contains(**t) && !sib.contains(**t)).count() as i64;
            2 * a + b
        };
        let score: HashMap<usize, i64> = found.iter().map(|&i| (i, specificity(i))).collect();

        // the person asked about is the one named first; several profiles may share it, so keep the longest name there
        let order: Vec<String> = self.word.find_iter(&fold(query)).map(|m| m.as_str().to_string()).collect();
        let matched = |i: usize| -> &HashSet<String> {
            let p = &self.people[i].1;
            let cands: Vec<&HashSet<String>> = [&p.name_tok, &p.slug_tok].into_iter().filter(|s| subset(s)).collect();
            // max by length, first wins on ties (as Python's max)
            let mut best: Option<&HashSet<String>> = None;
            for c in cands {
                if best.map_or(true, |b| c.len() > b.len()) {
                    best = Some(c);
                }
            }
            best.unwrap_or(&p.name_tok)
        };
        let first_pos = |i: usize| -> usize {
            let m = matched(i);
            if !subset(m) {
                return order.len();
            }
            m.iter().filter_map(|t| order.iter().position(|o| o == t)).min().unwrap_or(order.len())
        };
        let mlen = |i: usize| if subset(matched(i)) { matched(i).len() } else { 0 };
        let lead = *found.iter().min_by_key(|&&i| (first_pos(i), std::cmp::Reverse(mlen(i)))).unwrap();
        let key = (first_pos(lead), mlen(lead));
        found.retain(|&i| (first_pos(i), mlen(i)) == key);
        found.sort_by_key(|&i| (std::cmp::Reverse(score[&i]), std::cmp::Reverse(self.people[i].1.n)));

        let id = |i: usize| self.people[i].0.clone();
        let (top, rest) = (found[0], &found[1..]);
        let single = found.len() == 1
            || score[&top] > score[&rest[0]]
            || self.people[top].1.n as f64 >= self.dominance * self.people[rest[0]].1.n as f64;
        if !single {
            let ties: Vec<String> = found.iter().filter(|&&i| score[&i] == score[&top]).take(3).map(|&i| id(i)).collect();
            return Link { status: "ambiguous", candidates: ties, filter: false, alternatives: vec![] };
        }
        let also: Vec<String> = found.iter().filter(|&&i| i != top).take(2).map(|&i| id(i)).collect();
        let generic = self.people[top].1.generic;
        Link { status: if generic { "generic" } else { "single" }, candidates: vec![id(top)], filter: !generic, alternatives: also }
    }
}
