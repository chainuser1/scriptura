//! Engine facade: owns every store and answers JSON requests with JSON responses (the shape the C ABI and Dart use).
//! The engine returns verse IDs and scores only; text, references and localisation come from the repository.

use crate::encoder::Encoder;
use crate::entities::PeopleIndex;
use crate::focus::{Focus, RerankerFamily};
use crate::identity;
use crate::phrase::PhraseIndex;
use crate::reference::{Catalog, Reference};
use crate::search::{Index, Weights};
use crate::topics::TopicIndex;
use crate::tokenizer::QueryTokenizer;
use serde::Deserialize;
use serde_json::{json, Value};
use std::collections::{BTreeMap, HashMap, HashSet};
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Instant;

pub const MAX_TOKENS: usize = 512;
const PERSON_BOOST: f64 = 3.0;

#[derive(Deserialize)]
pub struct Config {
    pub retrieval_dir: PathBuf,
    pub head_npz: PathBuf,
    pub encoder_model: PathBuf,
    pub tokenizer_json: PathBuf,
    pub pack_dir: Option<PathBuf>,
    /// ONNX Runtime library to load (Android); ignored when it is linked into the engine.
    pub ort_library: Option<String>,
    pub phrase_db: Option<PathBuf>,
    pub catalog_db: Option<PathBuf>,
    pub entities_db: Option<PathBuf>,
    /// Optional topics pack database; adds the topic lane to similar verses.
    pub topics_db: Option<PathBuf>,
    /// Volume balance strength (crate::balance; 0 = off). The app passes the value chosen in tool/volume_balance.py.
    #[serde(default)]
    pub volume_balance: f64,
    /// Answer focus pack (model.onnx, tokenizer.json); optional. A model that fails to open leaves search untouched.
    #[serde(default)]
    pub focus_model: Option<PathBuf>,
    #[serde(default)]
    pub focus_tokenizer: Option<PathBuf>,
    /// "gpu" (graphics chip when it works, else CPU) or "cpu".
    #[serde(default)]
    pub focus_device: Option<String>,
    /// profile id -> [echo, spark, thread, root]
    pub profiles: BTreeMap<String, [f64; 4]>,
    pub default_profile: String,
    pub fallback_without_thread: String,
    #[serde(default = "one")]
    pub threads: usize,
    /// Artifact identities (see tool/config_identity.py); hashed into every response's configurationId.
    #[serde(default)]
    pub identity: Value,
}

fn one() -> usize {
    1
}

enum FocusSlot {
    NotLoaded { model: PathBuf, tokenizer: PathBuf, threads: usize, gpu: bool },
    Ready(Focus),
    Failed(String),
}

pub struct Engine {
    tok: QueryTokenizer,
    enc: Mutex<Encoder>,
    index: Index,
    trails: crate::trails::TrailModel,
    volumes: Option<crate::balance::Volumes>,
    balance_default: f64,
    phrase: Option<PhraseIndex>,
    catalog: Option<Catalog>,
    people: Option<PeopleIndex>,
    topics: Option<TopicIndex>,
    /// None: not configured. Opened on the first focus request, so the model only takes memory once it is used.
    focus: Option<Mutex<FocusSlot>>,
    profiles: BTreeMap<String, Weights>,
    default_profile: String,
    fallback: String,
    identity: Value,
    active: Mutex<HashMap<u64, Arc<AtomicBool>>>,
}

type Fail = (&'static str, String);

fn fail<T>(code: &'static str, msg: impl Into<String>) -> Result<T, Fail> {
    Err((code, msg.into()))
}

fn internal(e: String) -> Fail {
    if e == "cancelled" {
        ("cancelled", "request cancelled".into())
    } else {
        ("internal", e)
    }
}

impl Engine {
    pub fn open(cfg: Config) -> Result<Self, String> {
        if let Some(lib) = &cfg.ort_library {
            crate::encoder::set_ort_library(lib.clone());
        }
        let pack = cfg.pack_dir.as_deref().filter(|p| p.join("shard-0000.vec.npy").exists());
        let index = Index::open(&cfg.retrieval_dir, &cfg.head_npz, pack)?;
        let trails = crate::trails::TrailModel::build(&index);
        let volumes = crate::balance::Volumes::open_embedded(&index);
        if !(0.0..=1.0).contains(&cfg.volume_balance) {
            return Err(format!("volume_balance must be between 0 and 1, not {}", cfg.volume_balance));
        }
        let profiles: BTreeMap<String, Weights> = cfg
            .profiles
            .iter()
            .map(|(k, w)| (k.clone(), Weights { echo: w[0], spark: w[1], thread: w[2], root: w[3] }))
            .collect();
        for p in [&cfg.default_profile, &cfg.fallback_without_thread] {
            if !profiles.contains_key(p) {
                return Err(format!("profile {p:?} is not defined"));
            }
        }
        Ok(Self {
            tok: QueryTokenizer::from_file(&cfg.tokenizer_json)?,
            enc: Mutex::new(Encoder::open(&cfg.encoder_model, cfg.threads.max(1))?),
            index,
            trails,
            volumes,
            balance_default: cfg.volume_balance,
            phrase: cfg.phrase_db.as_deref().map(PhraseIndex::open).transpose()?,
            catalog: cfg.catalog_db.as_deref().map(Catalog::open).transpose()?,
            people: cfg.entities_db.as_deref().filter(|p| p.exists()).map(PeopleIndex::open).transpose()?,
            topics: cfg.topics_db.as_deref().filter(|p| p.exists()).map(TopicIndex::open).transpose()?,
            profiles,
            default_profile: cfg.default_profile,
            fallback: cfg.fallback_without_thread,
            identity: cfg.identity,
            focus: match (&cfg.focus_model, &cfg.focus_tokenizer) {
                (Some(m), Some(t)) => Some(Mutex::new(FocusSlot::NotLoaded {
                    model: m.clone(),
                    tokenizer: t.clone(),
                    threads: cfg.threads.max(1),
                    gpu: cfg.focus_device.as_deref() == Some("gpu"),
                })),
                _ => None,
            },
            active: Mutex::new(HashMap::new()),
        })
    }

    pub fn cancel(&self, request_id: u64) {
        if let Some(flag) = self.active.lock().unwrap().get(&request_id) {
            flag.store(true, Ordering::SeqCst);
        }
    }

    /// Always returns a JSON object: either the result or {"error": {"code", "message"}}.
    pub fn handle(&self, req: &Value) -> Value {
        let id = req.get("request_id").and_then(Value::as_u64);
        let flag = Arc::new(AtomicBool::new(false));
        if let Some(i) = id {
            self.active.lock().unwrap().insert(i, flag.clone());
        }
        let out = match self.dispatch(req, &flag) {
            Ok(mut v) => {
                if let (Some(i), Some(o)) = (id, v.as_object_mut()) {
                    o.insert("request_id".into(), json!(i));
                }
                v
            }
            Err((code, message)) => json!({"error": {"code": code, "message": message}, "request_id": id}),
        };
        if let Some(i) = id {
            self.active.lock().unwrap().remove(&i);
        }
        out
    }

    fn dispatch(&self, req: &Value, cancel: &Arc<AtomicBool>) -> Result<Value, Fail> {
        let op = req.get("op").and_then(Value::as_str).unwrap_or("");
        match op {
            "info" => Ok(self.info()),
            "search" => self.search(req, cancel, true),
            "semantic" => self.search(req, cancel, false),
            "phrase" => self.phrase_op(req),
            "similar" => self.similar_op(req),
            "reference" => {
                let c = self.catalog.as_ref().ok_or(("missing_pack", "catalog is not installed".to_string()))?;
                let text = req.get("text").and_then(Value::as_str).unwrap_or("");
                Ok(json!({"mode": "reference", "reference": c.parse(text, lang(req))}))
            }
            "trail_next" => self.trail_op(req),
            "explain" => self.explain_op(req),
            "focus" => self.focus_op(req, cancel),
            "device_trial" => self.device_trial(req),
            "taste" => crate::trails::taste(&self.index, &self.trails, req).map_err(|m| ("invalid_input", m)),
            other => fail("invalid_input", format!("unknown op {other:?}")),
        }
    }

    fn focus_op(&self, req: &Value, cancel: &Arc<AtomicBool>) -> Result<Value, Fail> {
        let Some(slot) = &self.focus else {
            return fail("focus_unavailable", "Answer focus is not installed".to_string());
        };
        let query = req.get("query").and_then(Value::as_str).ok_or(("invalid_input", "query is required".to_string()))?;
        let texts: Vec<&str> = req
            .get("texts")
            .and_then(Value::as_array)
            .ok_or(("invalid_input", "texts is required".to_string()))?
            .iter()
            .map(|t| t.as_str().ok_or(("invalid_input", "texts must be strings".to_string())))
            .collect::<Result<_, _>>()?;
        let started = Instant::now();
        let mut slot = slot.lock().unwrap();
        if let FocusSlot::NotLoaded { model, tokenizer, threads, gpu } = &*slot {
            // Task 1 only generalizes Focus's tokenization; every caller here still means Ezra until Task 2
            // threads a configured family through Config/FocusSlot.
            *slot = match Focus::open(model, tokenizer, *threads, *gpu, RerankerFamily::Ezra) {
                Ok(f) => FocusSlot::Ready(f),
                Err(e) => FocusSlot::Failed(e),
            };
        }
        let f = match &mut *slot {
            FocusSlot::Ready(f) => f,
            FocusSlot::Failed(e) => return fail("focus_unavailable", format!("Answer focus could not start: {e}")),
            FocusSlot::NotLoaded { .. } => unreachable!(),
        };
        let scores = f.score(query, &texts, cancel).map_err(|e| if e == "cancelled" { ("cancelled", e) } else { ("focus_failed", e) })?;
        Ok(json!({"mode": "focus", "scores": scores, "device": f.device(), "ms": started.elapsed().as_secs_f64() * 1000.0}))
    }

    /// How fast this machine runs the installed encoder (same size as the Answer focus model) and whether a graphics
    /// chip works through DirectML. The app turns this into its Answer focus choice before downloading anything.
    fn device_trial(&self, req: &Value) -> Result<Value, Fail> {
        let text = "And it came to pass that the people did hearken unto the words of the prophet and they did repent of their sins. ".repeat(4);
        let mut ids = self.tok.encode(&text).map_err(|e| ("trial_failed", e))?;
        ids.truncate(63);
        ids.push(2); // </s>: a 64-token passage
        let mut enc = self.enc.lock().unwrap();
        enc.encode(&ids).map_err(|e| ("trial_failed", e))?; // warm
        let started = Instant::now();
        for _ in 0..10 {
            enc.encode(&ids).map_err(|e| ("trial_failed", e))?;
        }
        // probe_gpu: false after an earlier trial never finished (a graphics driver that crashes must not crash every start)
        let probe = req.get("probe_gpu").and_then(Value::as_bool).unwrap_or(true);
        Ok(json!({"mode": "device_trial", "cpu_ms": started.elapsed().as_secs_f64() * 1000.0, "gpu": probe && crate::focus::gpu_available()}))
    }

    pub fn info(&self) -> Value {
        let has_pack = self.index.has_pack();
        let profiles: Vec<Value> = self
            .profiles
            .iter()
            .map(|(k, w)| json!({"id": k, "weights": [w.echo, w.spark, w.thread, w.root], "available": has_pack || w.thread == 0.0}))
            .collect();
        json!({
            "version": env!("CARGO_PKG_VERSION"), "verses": self.index.verse_ids.len(), "colbert_pack": has_pack,
            "phrase_languages": self.phrase.as_ref().map(|p| p.languages()).unwrap_or_default(),
            "catalog_languages": self.catalog.as_ref().map(|c| c.languages.clone()).unwrap_or_default(),
            "entities": self.people.is_some(), "topics": self.topics.is_some(), "volume_balance": self.volumes.is_some(), "profiles": profiles, "default_profile": self.default_profile,
            "focus": match self.focus.as_ref().map(|m| m.try_lock()) {
                None => "not installed",
                Some(Err(_)) => "busy",
                Some(Ok(slot)) => match &*slot {
                    FocusSlot::NotLoaded { .. } => "not loaded",
                    FocusSlot::Ready(f) => f.device(),
                    FocusSlot::Failed(_) => "failed",
                },
            },
        })
    }

    fn mask(&self, req: &Value) -> Result<Option<Vec<bool>>, Fail> {
        match req.get("filter") {
            None | Some(Value::Null) => Ok(None),
            Some(Value::Array(a)) => {
                let mut ranges = Vec::new();
                for r in a {
                    let p = r.as_array().filter(|p| p.len() == 2).and_then(|p| Some((p[0].as_i64()?, p[1].as_i64()?)));
                    match p {
                        Some(x) => ranges.push(x),
                        None => return fail("invalid_input", "filter must be a list of [first_verse_id, last_verse_id]"),
                    }
                }
                Ok(Some(self.index.mask_from_ranges(&ranges)))
            }
            Some(_) => fail("invalid_input", "filter must be a list of [first_verse_id, last_verse_id]"),
        }
    }

    /// The volume balance this request asks for: the request's `volume_balance` (0..=1), else the engine default.
    /// None when it is 0 or the volume table does not fit the index.
    fn balance_for(&self, req: &Value) -> Result<Option<(&crate::balance::Volumes, f64)>, Fail> {
        let s = match req.get("volume_balance") {
            None | Some(Value::Null) => self.balance_default,
            Some(v) => match v.as_f64() {
                Some(x) if (0.0..=1.0).contains(&x) => x,
                _ => return fail("invalid_input", format!("volume_balance must be a number between 0 and 1, not {v}")),
            },
        };
        Ok(self.volumes.as_ref().filter(|_| s > 0.0).map(|v| (v, s)))
    }

    fn filter_ids(&self, mask: &Option<Vec<bool>>) -> Option<Vec<i64>> {
        mask.as_ref().map(|m| self.index.verse_ids.iter().zip(m).filter(|(_, &a)| a).map(|(&v, _)| v).collect())
    }

    fn top_k(req: &Value) -> usize {
        req.get("top_k").and_then(Value::as_u64).map(|k| k.clamp(1, 200) as usize).unwrap_or(20)
    }

    fn config_id(&self, mode: &str, weights: Option<&Weights>, filter_sha: Option<String>) -> String {
        self.config_id_balanced(mode, weights, filter_sha, 0.0)
    }

    /// The configuration id; a volume balance strength above 0 is part of it (0 keeps today's ids).
    fn config_id_balanced(&self, mode: &str, weights: Option<&Weights>, filter_sha: Option<String>, s: f64) -> String {
        let mut parts = self.identity.as_object().cloned().unwrap_or_default();
        if s > 0.0 {
            parts.insert("volume_balance".into(), json!({"strength": s, "top_frac": crate::balance::TOP_FRAC, "min_top": crate::balance::MIN_TOP}));
        }
        if let Some(w) = weights {
            let mut fusion = parts.get("fusion").and_then(Value::as_object).cloned().unwrap_or_default();
            fusion.insert("weights".into(), json!({"dense": w.echo, "sparse": w.spark, "colbert": w.thread, "genome": w.root}));
            parts.insert("fusion".into(), Value::Object(fusion));
        }
        parts.insert("filter_sha256".into(), json!(filter_sha));
        identity::configuration_id(&Value::Object(parts), mode)
    }

    fn search(&self, req: &Value, cancel: &Arc<AtomicBool>, smart: bool) -> Result<Value, Fail> {
        let t0 = Instant::now();
        let query = req.get("query").and_then(Value::as_str).unwrap_or("").trim().to_string();
        if query.is_empty() {
            return fail("invalid_input", "empty query");
        }
        let language = lang(req);
        let top_k = Self::top_k(req);
        let mut interpretation = serde_json::Map::new();

        if smart {
            if let Some(c) = &self.catalog {
                match c.parse(&query, language) {
                    Reference::NotAReference => {}
                    r => return Ok(json!({"mode": "reference", "reference": r, "interpretation": {"kind": "reference"}})),
                }
            }
        }
        let picked = req.get("person").and_then(Value::as_str);
        let link = if smart {
            self.people.as_ref().map(|p| (p, picked.and_then(|id| p.forced(id)).unwrap_or_else(|| p.link(&query))))
        } else {
            None
        };
        if let Some((p, l)) = &link {
            if l.status != "none" {
                let chips: Vec<Value> = l.candidates.iter().chain(l.alternatives.iter())
                    .map(|id| {
                        let (name, qual) = p.display(id).unwrap_or(("", ""));
                        json!({"entity_id": id, "name": name, "qualifier": qual, "selected": l.candidates.contains(id)})
                    })
                    .collect();
                interpretation.insert("person".into(), json!({"status": l.status, "people": chips, "applied": l.filter}));
            }
        }

        // profile: requested or default; a profile that needs ColBERT falls back when the pack is not installed
        let wanted = req.get("profile").and_then(Value::as_str).unwrap_or(&self.default_profile);
        let Some(mut weights) = self.profiles.get(wanted).copied() else {
            return fail("invalid_input", format!("unknown profile {wanted:?}"));
        };
        let mut used = wanted.to_string();
        if weights.thread > 0.0 && !self.index.has_pack() {
            used = self.fallback.clone();
            weights = self.profiles[&used];
        }

        let ids = self.tok.encode(&query).map_err(internal)?;
        if ids.len() > MAX_TOKENS {
            return fail("invalid_input", format!("query has {} tokens; the limit is {MAX_TOKENS}", ids.len()));
        }
        if cancel.load(Ordering::SeqCst) {
            return fail("cancelled", "request cancelled");
        }
        let te = Instant::now();
        let encoded = self.enc.lock().unwrap().encode(&ids).map_err(|e| ("inference_failure", e))?;
        let encode_ms = te.elapsed().as_secs_f64() * 1000.0;
        let mask = self.mask(req)?;
        let vb = self.balance_for(req)?;
        let ts = Instant::now();
        let is_cancelled = || cancel.load(Ordering::SeqCst);
        let want_lanes = req.get("lanes").and_then(Value::as_bool).unwrap_or(false);
        let want_concentration = req.get("concentration").and_then(Value::as_bool).unwrap_or(false);
        let mut out = self.index.search_balanced(&encoded, &weights, top_k.max(if link.is_some() { 60 } else { 0 }), mask.as_deref(), &is_cancelled, vb, want_lanes, want_concentration)
            .map_err(internal)?;

        // person questions: the linked person's verses first, ordered by the engine's own score
        if let Some((p, l)) = &link {
            if l.filter {
                let set: HashSet<i64> = p.verses_of(&l.candidates[0]).iter().copied().collect();
                for h in out.hits.iter_mut() {
                    if set.contains(&h.verse_id) {
                        h.score += PERSON_BOOST;
                    }
                }
                out.hits.sort_by(|a, b| b.score.partial_cmp(&a.score).unwrap().then(a.verse_id.cmp(&b.verse_id)));
            }
        }
        out.hits.truncate(top_k);
        let search_ms = ts.elapsed().as_secs_f64() * 1000.0;
        let fsha = identity::filter_hash(self.filter_ids(&mask).as_deref());
        Ok(json!({
            "mode": "semantic",
            "hits": out.hits.iter().map(|h| {
                let mut v = json!({"verse_id": h.verse_id, "score": h.score});
                if let Some([d, s, c, g]) = h.lanes {
                    let mut lanes = json!({"dense": d, "sparse": s, "colbert": c, "genome": g});
                    if let Some(conc) = h.concentration {
                        lanes["concentration"] = json!(conc);
                    }
                    v["lanes"] = lanes;
                }
                v
            }).collect::<Vec<_>>(),
            "candidates": out.candidates,
            "profile": used, "requested_profile": wanted,
            "interpretation": interpretation,
            "configuration_id": self.config_id_balanced("semantic", Some(&weights), fsha, vb.map_or(0.0, |b| b.1)),
            "timings_ms": {"encode": encode_ms, "search": search_ms, "total": t0.elapsed().as_secs_f64() * 1000.0},
        }))
    }

    fn phrase_op(&self, req: &Value) -> Result<Value, Fail> {
        let p = self.phrase.as_ref().ok_or(("missing_pack", "phrase index is not installed".to_string()))?;
        let phrase = req.get("phrase").and_then(Value::as_str).unwrap_or("");
        let mask = self.mask(req)?;
        let allowed: Option<HashSet<i64>> = self.filter_ids(&mask).map(|v| v.into_iter().collect());
        let r = p.search(phrase, lang(req), Self::top_k(req), allowed.as_ref())?;
        Ok(json!({
            "mode": "phrase", "verse_ids": r.verse_ids, "total": r.total, "truncated": r.truncated,
            "configuration_id": self.config_id("phrase", None, identity::filter_hash(self.filter_ids(&mask).as_deref())),
        }))
    }

    /// Genome cosine fused with the topic lane: z-scores over the union of each lane's top `lane_k` candidates.
    fn similar_with_topics(&self, v: i64, top: usize, allowed: Option<&[bool]>, vb: Option<(&crate::balance::Volumes, f64)>) -> Result<Value, Fail> {
        let t = self.topics.as_ref().unwrap();
        let (row, mut g) = self.index.genome_scores(v).map_err(|e| {
            if e.starts_with("unknown verse") { ("unknown_verse", e) } else { ("internal", e) }
        })?;
        let ids = &self.index.verse_ids;
        let ok = |r: usize| r != row && allowed.map_or(true, |m| m[r]);
        let rows: Vec<usize> = (0..g.len()).filter(|&r| ok(r)).collect();
        let mut tscore = vec![0.0f64; g.len()];
        let mut topic_rows = Vec::new();
        for (u, s) in t.scores(v) {
            if let Some(r) = self.index.row_of(u) {
                if ok(r) {
                    tscore[r] = s;
                    topic_rows.push(r);
                }
            }
        }
        if let Some((vol, strength)) = vb {
            // topic_rows (who is in the topic lane) was taken from the raw overlap above
            vol.balance(&mut g, &ok, strength, false);
            vol.balance(&mut tscore, &ok, strength, true);
        }
        let mut cand: Vec<usize> = crate::kernels::top_k(&g, ids, Some(&rows), t.lane_k);
        cand.extend(crate::kernels::top_k(&tscore, ids, Some(&topic_rows), t.lane_k));
        cand.sort_unstable();
        cand.dedup();
        let zg = crate::kernels::zscore(&cand.iter().map(|&r| g[r]).collect::<Vec<_>>());
        let zt = crate::kernels::zscore(&cand.iter().map(|&r| tscore[r]).collect::<Vec<_>>());
        let mut fused = vec![0.0f64; g.len()];
        for (i, &r) in cand.iter().enumerate() {
            fused[r] = zg[i] + t.weight * zt[i];
        }
        let order = crate::kernels::top_k(&fused, ids, Some(&cand), top);
        let fsha = identity::filter_hash(self.filter_ids(&allowed.map(|m| m.to_vec())).as_deref());
        let mut parts = self.identity.as_object().cloned().unwrap_or_default();
        parts.insert("topics".into(), json!({"sha256": t.sha256, "weight": t.weight, "lane_k": t.lane_k}));
        parts.insert("filter_sha256".into(), json!(fsha));
        if let Some((_, s)) = vb {
            parts.insert("volume_balance".into(), json!({"strength": s, "top_frac": crate::balance::TOP_FRAC, "min_top": crate::balance::MIN_TOP}));
        }
        Ok(json!({
            "mode": "similar", "profile": "genome_topics_v1",
            "hits": order.iter().map(|&r| json!({"verse_id": ids[r], "score": fused[r]})).collect::<Vec<_>>(),
            "configuration_id": identity::configuration_id(&Value::Object(parts), "similar_topics"),
        }))
    }

    fn trail_op(&self, req: &Value) -> Result<Value, Fail> {
        let text = |t: &str| -> Result<Vec<f32>, String> {
            let ids = self.tok.encode(t)?;
            if ids.len() > MAX_TOKENS {
                return Err(format!("the question has {} tokens; the limit is {MAX_TOKENS}", ids.len()));
            }
            let enc = self.enc.lock().unwrap().encode(&ids)?;
            Ok(self.index.predicted_genome(&enc.dense))
        };
        let entity = |id: &str| -> Vec<i64> { self.people.as_ref().map(|p| p.verses_of(id).to_vec()).unwrap_or_default() };
        let vb = self.balance_for(req)?;
        let mut out = crate::trails::trail_next(&self.index, &self.trails, self.topics.as_ref(), req, &text, &entity, vb)
            .map_err(|m| ("invalid_input", m))?;
        let mut parts = self.identity.as_object().cloned().unwrap_or_default();
        if let Some(t) = &self.topics {
            parts.insert("topics".into(), json!({"sha256": t.sha256, "weight": t.weight, "lane_k": t.lane_k}));
        }
        if let Some((_, s)) = vb {
            parts.insert("volume_balance".into(), json!({"strength": s, "top_frac": crate::balance::TOP_FRAC, "min_top": crate::balance::MIN_TOP}));
        }
        out["configuration_id"] = json!(identity::configuration_id(&Value::Object(parts), "trail"));
        Ok(out)
    }

    fn explain_op(&self, req: &Value) -> Result<Value, Fail> {
        let piece = |id: u32| self.tok.piece(id);
        let people = self.people.as_ref();
        let shared = |a: i64, b: i64| -> Vec<Value> {
            let Some(p) = people else { return vec![] };
            let (ea, eb) = (p.entities_of(a), p.entities_of(b));
            ea.iter()
                .filter(|x| eb.contains(x))
                .take(3)
                .map(|id| json!({"id": id, "name": p.display(id).map(|d| d.0).unwrap_or("")}))
                .collect()
        };
        crate::trails::explain(&self.index, &self.trails, req, &piece, &shared).map_err(|m| ("invalid_input", m))
    }

    fn similar_op(&self, req: &Value) -> Result<Value, Fail> {
        let Some(v) = req.get("verse_id").and_then(Value::as_i64) else {
            return fail("invalid_input", "verse_id is required");
        };
        let mask = self.mask(req)?;
        let vb = self.balance_for(req)?;
        let use_topics = self.topics.is_some() && req.get("topics").and_then(Value::as_bool).unwrap_or(true);
        if use_topics {
            return self.similar_with_topics(v, Self::top_k(req).min(100), mask.as_deref(), vb);
        }
        if let Some((vol, strength)) = vb {
            let unknown = |e: String| if e.starts_with("unknown verse") { ("unknown_verse", e) } else { ("internal", e) };
            let (row, mut g) = self.index.genome_scores(v).map_err(unknown)?;
            let ok = |r: usize| r != row && mask.as_deref().map_or(true, |m| m[r]);
            vol.balance(&mut g, &ok, strength, false);
            let rows: Vec<usize> = (0..g.len()).filter(|&r| ok(r)).collect();
            let order = crate::kernels::top_k(&g, &self.index.verse_ids, Some(&rows), Self::top_k(req).min(100));
            return Ok(json!({
                "mode": "similar", "profile": "genome_weighted_cosine_v1",
                "hits": order.iter().map(|&r| json!({"verse_id": self.index.verse_ids[r], "score": g[r]})).collect::<Vec<_>>(),
                "configuration_id": self.config_id_balanced("similar", None, identity::filter_hash(self.filter_ids(&mask).as_deref()), strength),
            }));
        }
        let hits = self.index.similar(v, Self::top_k(req).min(100), mask.as_deref()).map_err(|e| {
            if e.starts_with("unknown verse") { ("unknown_verse", e) } else { ("internal", e) }
        })?;
        Ok(json!({
            "mode": "similar", "profile": "genome_weighted_cosine_v1",
            "hits": hits.iter().map(|h| json!({"verse_id": h.verse_id, "score": h.score})).collect::<Vec<_>>(),
            "configuration_id": self.config_id("similar", None, identity::filter_hash(self.filter_ids(&mask).as_deref())),
        }))
    }
}

fn lang(req: &Value) -> &str {
    req.get("language").and_then(Value::as_str).unwrap_or("english")
}
