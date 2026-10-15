//! Trails (spec 2026-10-14-trails-design.md sections 5 and 6). Pure functions of a request and the installed packs.
//! The behaviour is defined by tool/trails.py; test/golden/trails.json pins this port to it.

use crate::kernels::{dot_rows_f32, top_k, zscore};
use crate::search::Index;
use crate::topics::TopicIndex;
use serde_json::{json, Value};
use std::collections::{HashMap, HashSet};

const FAMILIES: usize = 23;
const LANE_K: usize = 200;
const WIDE_K: usize = 500;
const NEAR_DISLIKE: f64 = 0.90;
const LEARN: f64 = 0.5;
const CLIP: f64 = 2.0;
const TASTE: f64 = 0.3;
const TOPIC_W: f64 = 0.5;
const MOOD_MU: f64 = 0.6;
const EXCLUDED_FAMILY: usize = 16; // Q: weight 0, never dominant

pub struct TrailModel {
    family: Vec<usize>,
    e: Vec<f64>, // [n, 23] family energy
    ebar: [f64; FAMILIES],
    dominant: Vec<usize>,
    gene_index: HashMap<String, usize>,
}

impl TrailModel {
    pub fn build(index: &Index) -> Self {
        let genes = index.genes();
        let family: Vec<usize> = index.gene_ids().iter().map(|g| (g.as_bytes()[0] - b'A') as usize).collect();
        let n = index.verse_ids.len();
        let mut e = vec![0.0f64; n * FAMILIES];
        for r in 0..n {
            let row = index.genome_row(r);
            for i in 0..genes {
                let v = f64::from(row[i]);
                e[r * FAMILIES + family[i]] += v * v;
            }
        }
        let mut ebar = [0.0f64; FAMILIES];
        for r in 0..n {
            for k in 0..FAMILIES {
                ebar[k] += e[r * FAMILIES + k];
            }
        }
        ebar.iter_mut().for_each(|x| *x /= n as f64);
        let dominant: Vec<usize> = (0..n)
            .map(|r| {
                let mut best = 0;
                for k in 1..FAMILIES {
                    if e[r * FAMILIES + k] > e[r * FAMILIES + best] {
                        best = k;
                    }
                }
                best
            })
            .collect();
        let gene_index = index.gene_ids().iter().enumerate().map(|(i, g)| (g.clone(), i)).collect();
        Self { family, e, ebar, dominant, gene_index }
    }

    fn energy(&self, row: usize) -> &[f64] {
        &self.e[row * FAMILIES..(row + 1) * FAMILIES]
    }
}

fn normalise(v: &mut [f64]) {
    let n = v.iter().map(|x| x * x).sum::<f64>().sqrt();
    if n > 1e-12 {
        v.iter_mut().for_each(|x| *x /= n);
    }
}

fn norm(v: &[f64]) -> f64 {
    v.iter().map(|x| x * x).sum::<f64>().sqrt()
}

fn to_f32(v: &[f64]) -> Vec<f32> {
    v.iter().map(|&x| x as f32).collect()
}

fn dots(index: &Index, q: &[f32]) -> Vec<f64> {
    dot_rows_f32(index.genome_matrix(), index.genes(), q).into_iter().map(f64::from).collect()
}

fn seed_vec(
    index: &Index,
    v: &Value,
    text: &dyn Fn(&str) -> Result<Vec<f32>, String>,
    entity: &dyn Fn(&str) -> Vec<i64>,
) -> Result<Vec<f64>, String> {
    let genes = index.genes();
    if let Some(eid) = v.get("entity_id").and_then(Value::as_str) {
        // a person, place or group seed is the mean genome of the entity's linked verses
        let verses: Vec<Value> = entity(eid).into_iter().map(|x| json!(x)).collect();
        return seed_vec(index, &json!({ "verses": verses }), text, entity);
    }
    if let Some(id) = v.get("verse_id").and_then(Value::as_i64) {
        let r = index.row_of(id).ok_or_else(|| format!("unknown verse id {id}"))?;
        return Ok(index.genome_row(r).iter().map(|&x| f64::from(x)).collect());
    }
    if let Some(g) = v.get("genome").and_then(Value::as_array) {
        let mut x: Vec<f64> = g.iter().filter_map(Value::as_f64).collect();
        if x.len() != genes {
            return Err(format!("genome must have {genes} numbers"));
        }
        normalise(&mut x);
        return Ok(x);
    }
    if let Some(ids) = v.get("verses").and_then(Value::as_array) {
        let mut acc = vec![0.0f64; genes];
        let mut count = 0.0;
        for id in ids.iter().filter_map(Value::as_i64) {
            if let Some(r) = index.row_of(id) {
                index.genome_row(r).iter().enumerate().for_each(|(i, &x)| acc[i] += f64::from(x));
                count += 1.0;
            }
        }
        if count == 0.0 {
            return Err("no known verses in the seed".into());
        }
        acc.iter_mut().for_each(|x| *x /= count);
        normalise(&mut acc);
        return Ok(acc);
    }
    if let Some(t) = v.get("text").and_then(Value::as_str) {
        let mut g: Vec<f64> = text(t)?.iter().map(|&x| f64::from(x)).collect();
        normalise(&mut g);
        return Ok(g);
    }
    Err("seed needs verse_id, genome, verses or text".into())
}

fn mood_vector(index: &Index, model: &TrailModel, moods: &Value) -> Result<Option<Vec<f64>>, String> {
    let Some(list) = moods.as_array().filter(|l| !l.is_empty()) else { return Ok(None) };
    let genes = index.genes();
    let mut m = vec![0.0f64; genes];
    for mood in list {
        let mut v = vec![0.0f64; genes];
        for g in mood.as_array().ok_or("a mood is a list of genes")? {
            let id = g.get("id").and_then(Value::as_str).ok_or("mood gene needs an id")?;
            let w = g.get("weight").and_then(Value::as_f64).unwrap_or(1.0);
            let i = *model.gene_index.get(id).ok_or_else(|| format!("unknown gene {id}"))?;
            v[i] = w * f64::from(index.sw()[i]);
        }
        normalise(&mut v);
        m.iter_mut().zip(&v).for_each(|(a, b)| *a += b);
    }
    normalise(&mut m);
    Ok(Some(m))
}

pub fn trail_next(
    index: &Index,
    model: &TrailModel,
    topics: Option<&TopicIndex>,
    req: &Value,
    text: &dyn Fn(&str) -> Result<Vec<f32>, String>,
    entity: &dyn Fn(&str) -> Vec<i64>,
    balance: Option<(&crate::balance::Volumes, f64)>,
) -> Result<Value, String> {
    let n = index.verse_ids.len();
    let ids = &index.verse_ids;
    let k = req.get("k").and_then(Value::as_u64).unwrap_or(10).clamp(1, 50) as usize;
    let focus = req.get("focus").and_then(Value::as_f64).unwrap_or(0.5).clamp(0.0, 1.0);
    let mood_strength = req.get("mood_strength").and_then(Value::as_f64).unwrap_or(0.5).clamp(0.0, 1.0);
    let events: &[Value] = req.get("events").and_then(Value::as_array).map(Vec::as_slice).unwrap_or(&[]);
    let step = req.get("step").and_then(Value::as_i64).unwrap_or(events.len() as i64);

    // replay the log
    let mut w = [0.0f64; FAMILIES];
    let (mut liked, mut disliked, mut skipped, mut seen_events): (Vec<usize>, Vec<usize>, Vec<usize>, Vec<usize>) =
        (vec![], vec![], vec![], vec![]);
    for e in events {
        let (Some(id), Some(action)) = (e.get("verse_id").and_then(Value::as_i64), e.get("action").and_then(Value::as_str)) else {
            continue;
        };
        let Some(r) = index.row_of(id) else { continue };
        if !seen_events.contains(&r) {
            seen_events.push(r);
        }
        let reward = match action {
            "like" => 1.0,
            "skip" => -0.2,
            "dislike" => -1.0,
            _ => continue,
        };
        let en = model.energy(r);
        for kk in 0..FAMILIES {
            w[kk] = (w[kk] + LEARN * reward * (en[kk] - model.ebar[kk])).clamp(-CLIP, CLIP);
        }
        match action {
            "like" => liked.push(r),
            "dislike" => disliked.push(r),
            _ => skipped.push(r),
        }
    }

    let seed = req.get("seed").ok_or("seed is required")?;
    let g_seed = seed_vec(index, seed, text, entity)?;
    let extras: Vec<Value> = req.get("extra_seeds").and_then(Value::as_array).cloned().unwrap_or_default();
    let mut t = g_seed.clone();
    for x in &extras {
        let v = seed_vec(index, x, text, entity)?;
        t.iter_mut().zip(&v).for_each(|(a, b)| *a += b);
    }
    let add = |t: &mut Vec<f64>, rows: &[usize], scale: f64| {
        for &r in rows {
            index.genome_row(r).iter().enumerate().for_each(|(i, &x)| t[i] += scale * f64::from(x));
        }
    };
    add(&mut t, &liked, 1.0);
    add(&mut t, &disliked, -0.6);
    add(&mut t, &skipped, -0.2);
    if norm(&t) > 1e-12 {
        normalise(&mut t);
    } else {
        t = g_seed.clone();
    }
    let m = mood_vector(index, model, req.get("moods").unwrap_or(&Value::Null))?;
    let tp: Vec<f64> = match &m {
        Some(m) => {
            let mut v: Vec<f64> = t.iter().zip(m).map(|(a, b)| a + 0.5 * mood_strength * b).collect();
            normalise(&mut v);
            v
        }
        None => t.clone(),
    };

    // eligibility
    let mut seen: HashSet<usize> = seen_events.iter().copied().collect();
    let recent_ids: Vec<i64> = req.get("recent").and_then(Value::as_array).map(|a| a.iter().filter_map(Value::as_i64).collect()).unwrap_or_default();
    recent_ids.iter().filter_map(|&v| index.row_of(v)).for_each(|r| {
        seen.insert(r);
    });
    let mut seed_verses: Vec<i64> = vec![];
    if let Some(v) = seed.get("verse_id").and_then(Value::as_i64) {
        seed_verses.push(v);
    }
    for x in &extras {
        if let Some(v) = x.get("verse_id").and_then(Value::as_i64) {
            seed_verses.push(v);
        }
    }
    seed_verses.iter().filter_map(|&v| index.row_of(v)).for_each(|r| {
        seen.insert(r);
    });
    let mut allowed = vec![true; n];
    seen.iter().for_each(|&r| allowed[r] = false);
    if let Some(f) = req.get("filter").and_then(Value::as_array) {
        let ranges: Vec<(i64, i64)> = f.iter().filter_map(|p| Some((p.get(0)?.as_i64()?, p.get(1)?.as_i64()?))).collect();
        let mask = index.mask_from_ranges(&ranges);
        allowed.iter_mut().zip(&mask).for_each(|(a, m)| *a &= *m);
    }
    let mut near = vec![true; n];
    for &d in &disliked {
        let s = dots(index, index.genome_row(d));
        near.iter_mut().zip(&s).for_each(|(a, v)| *a &= *v < NEAR_DISLIKE);
    }

    let mut cos_t = dots(index, &to_f32(&t));
    let mut cos_p = dots(index, &to_f32(&tp));

    // topic overlap: the seeds' and liked verses' topic vectors, summed and normalised
    let mut overlap = vec![0.0f64; n];
    let mut topic_ok = false;
    if let Some(tp_index) = topics {
        let mut acc: Vec<(u32, f64)> = Vec::new();
        let add_verse = |acc: &mut Vec<(u32, f64)>, v: i64| {
            for &(tid, wt) in tp_index.vector_of(v) {
                match acc.iter_mut().find(|(a, _)| *a == tid) {
                    Some(slot) => slot.1 += f64::from(wt),
                    None => acc.push((tid, f64::from(wt))),
                }
            }
        };
        for &r in &liked {
            add_verse(&mut acc, ids[r]);
        }
        for &v in &seed_verses {
            add_verse(&mut acc, v);
        }
        let nrm = acc.iter().map(|(_, x)| x * x).sum::<f64>().sqrt();
        if nrm > 0.0 {
            topic_ok = true;
            for (tid, x) in &acc {
                for &(u, wu) in tp_index.postings_of(*tid) {
                    if let Some(r) = index.row_of(u) {
                        overlap[r] += (x / nrm) * f64::from(wu);
                    }
                }
            }
        }
    }

    // taken before balancing: balance must not change who is in the topic lane
    let has_topic: Vec<bool> = overlap.iter().map(|&x| x > 0.0).collect();
    if let Some((v, strength)) = balance {
        let ok = |r: usize| allowed[r];
        for lane in [&mut cos_t, &mut cos_p] {
            v.balance(lane, &ok, strength, false);
        }
        v.balance(&mut overlap, &ok, strength, true);
    }

    // candidate pool, widening instead of failing
    let mut widened = 0;
    let mut pool_k = LANE_K;
    let cand: Vec<usize> = loop {
        let elig: Vec<usize> = (0..n).filter(|&r| allowed[r] && (widened > 0 || near[r])).collect();
        let cg = top_k(&cos_p, ids, Some(&elig), pool_k);
        let ct = if topic_ok {
            let e2: Vec<usize> = elig.iter().copied().filter(|&r| has_topic[r]).collect();
            top_k(&overlap, ids, Some(&e2), pool_k)
        } else {
            vec![]
        };
        let mut c: Vec<usize> = cg.into_iter().chain(ct).collect();
        c.sort_unstable();
        c.dedup();
        if c.len() >= k.min(elig.len()) || widened >= 2 {
            break c;
        }
        widened += 1;
        if widened == 2 {
            pool_k = WIDE_K;
        }
    };
    let leans = |w: &[f64; FAMILIES]| -> Vec<String> {
        let mut order: Vec<usize> = (0..FAMILIES).collect();
        order.sort_by(|&a, &b| w[b].partial_cmp(&w[a]).unwrap().then(a.cmp(&b)));
        order.into_iter().take(2).filter(|&i| w[i] > 0.25).map(|i| ((b'A' + i as u8) as char).to_string()).collect()
    };
    if cand.is_empty() {
        return Ok(json!({"mode": "trail", "hits": [], "family_weights": w, "leans": leans(&w), "widened": widened, "candidates": 0}));
    }

    // score
    let zg = zscore(&cand.iter().map(|&r| cos_t[r]).collect::<Vec<_>>());
    let zt = if topic_ok { zscore(&cand.iter().map(|&r| overlap[r]).collect::<Vec<_>>()) } else { vec![0.0; cand.len()] };
    let taste: Vec<f64> = cand
        .iter()
        .map(|&r| TASTE * (0..FAMILIES).map(|kk| (model.energy(r)[kk] - model.ebar[kk]) * w[kk]).sum::<f64>())
        .collect();
    let nov_w = 0.1 + 0.3 * focus;
    let recent_rows: Vec<usize> = recent_ids[recent_ids.len().saturating_sub(5)..].iter().filter_map(|&v| index.row_of(v)).collect();
    let mut sims = vec![0.0f64; cand.len()];
    for (j, &rr) in recent_rows.iter().enumerate() {
        let s = dots(index, index.genome_row(rr));
        for (i, &r) in cand.iter().enumerate() {
            sims[i] = if j == 0 { s[r] } else { sims[i].max(s[r]) };
        }
    }
    let novelty: Vec<f64> = sims.iter().map(|s| nov_w * (1.0 - s)).collect();
    let mood: Vec<f64> = match &m {
        Some(m) => {
            let s = dots(index, &to_f32(m));
            zscore(&cand.iter().map(|&r| s[r]).collect::<Vec<_>>()).into_iter().map(|z| MOOD_MU * mood_strength * z).collect()
        }
        None => vec![0.0; cand.len()],
    };
    let topics_part: Vec<f64> = zt.iter().map(|z| TOPIC_W * z).collect();
    let score: Vec<f64> = (0..cand.len()).map(|i| zg[i] + topics_part[i] + taste[i] + novelty[i] + mood[i]).collect();
    let mut ranked: Vec<usize> = (0..cand.len()).collect();
    ranked.sort_by(|&a, &b| score[b].partial_cmp(&score[a]).unwrap().then(ids[cand[a]].cmp(&ids[cand[b]])));

    // deterministic exploration
    let cadence = ((8.0 - 5.0 * focus) + 0.5).floor().max(1.0) as i64;
    let mut counts = [0.0f64; FAMILIES];
    for &r in &seen_events {
        counts[model.dominant[r]] += 1.0;
    }
    let mut taken: HashSet<usize> = HashSet::new();
    let mut picks: Vec<(usize, bool)> = vec![];
    for j in 0..k.min(ranked.len()) {
        let mut choice: Option<usize> = None;
        let mut explore = false;
        if (step + j as i64 + 1) % cadence == 0 {
            let remaining: Vec<usize> = ranked.iter().copied().filter(|i| !taken.contains(i)).collect();
            let mut fams: Vec<usize> = remaining.iter().map(|&i| model.dominant[cand[i]]).filter(|&f| f != EXCLUDED_FAMILY).collect();
            fams.sort_by(|&a, &b| counts[a].partial_cmp(&counts[b]).unwrap().then(a.cmp(&b)));
            fams.dedup();
            if let Some(&want) = fams.first() {
                choice = remaining.iter().copied().find(|&i| model.dominant[cand[i]] == want);
                explore = choice.is_some();
            }
        }
        let c = choice.unwrap_or_else(|| ranked.iter().copied().find(|i| !taken.contains(i)).unwrap());
        taken.insert(c);
        counts[model.dominant[cand[c]]] += 1.0;
        picks.push((c, explore));
    }

    let hits: Vec<Value> = picks
        .iter()
        .map(|&(i, ex)| {
            json!({"verse_id": ids[cand[i]], "score": score[i],
                   "parts": {"genome": zg[i], "topics": topics_part[i], "taste": taste[i], "novelty": novelty[i], "mood": mood[i], "explore": ex}})
        })
        .collect();
    Ok(json!({"mode": "trail", "hits": hits, "family_weights": w, "leans": leans(&w), "widened": widened, "candidates": cand.len()}))
}

pub fn explain(
    index: &Index,
    model: &TrailModel,
    req: &Value,
    piece: &dyn Fn(u32) -> Option<String>,
    shared_entities: &dyn Fn(i64, i64) -> Vec<Value>,
) -> Result<Value, String> {
    let a_id = req.get("a").and_then(Value::as_i64).ok_or("a is required")?;
    let b_id = req.get("b").and_then(Value::as_i64).ok_or("b is required")?;
    let ra = index.row_of(a_id).ok_or_else(|| format!("unknown verse id {a_id}"))?;
    let rb = index.row_of(b_id).ok_or_else(|| format!("unknown verse id {b_id}"))?;
    let (a, b) = (index.genome_row(ra), index.genome_row(rb));
    let c: Vec<f64> = a.iter().zip(b).map(|(&x, &y)| f64::from(x) * f64::from(y)).collect();
    let mut fam_sum = [0.0f64; FAMILIES];
    for (i, &v) in c.iter().enumerate() {
        fam_sum[model.family[i]] += v.max(0.0);
    }
    let total: f64 = fam_sum.iter().sum();
    let mut families = vec![];
    if total > 1e-12 {
        let mut order: Vec<usize> = (0..FAMILIES).collect();
        order.sort_by(|&x, &y| fam_sum[y].partial_cmp(&fam_sum[x]).unwrap().then(x.cmp(&y)));
        for &kk in order.iter().take(3) {
            let share = fam_sum[kk] / total;
            if share < 0.05 {
                continue;
            }
            let mut idx: Vec<usize> = (0..c.len()).filter(|&i| model.family[i] == kk).collect();
            idx.sort_by(|&x, &y| c[y].partial_cmp(&c[x]).unwrap().then(x.cmp(&y)));
            let genes: Vec<Value> = idx
                .iter()
                .take(3)
                .filter(|&&i| c[i] > 0.0)
                .map(|&i| json!({"id": index.gene_ids()[i], "a": a[i], "b": b[i]}))
                .collect();
            families.push(json!({"family": ((b'A' + kk as u8) as char).to_string(), "share": share, "genes": genes}));
        }
    }
    let mut mood_matches: Vec<String> = req
        .get("mood_genes")
        .and_then(Value::as_array)
        .map(|l| l.iter().filter_map(Value::as_str).filter(|g| model.gene_index.contains_key(*g)).map(String::from).collect())
        .unwrap_or_default();
    mood_matches.sort_by(|x, y| {
        let (bx, by) = (b[model.gene_index[x]], b[model.gene_index[y]]);
        by.partial_cmp(&bx).unwrap().then(x.cmp(y))
    });
    mood_matches.retain(|g| b[model.gene_index[g]] > 0.0);
    mood_matches.truncate(3);

    // words both verses carry: whole words only, at least four letters, as they read in the text
    let mut terms: Vec<String> = Vec::new();
    for (tid, _) in index.shared_terms(ra, rb, 40) {
        if let Some(p) = piece(tid) {
            if let Some(word) = p.strip_prefix('\u{2581}') {
                let word = word.to_lowercase();
                if word.chars().count() >= 4 && word.chars().all(|ch| ch.is_alphabetic()) && !terms.contains(&word) {
                    terms.push(word);
                }
            }
        }
        if terms.len() == 5 {
            break;
        }
    }
    Ok(json!({"mode": "explain", "families": families, "mood_matches": mood_matches, "shared_terms": terms,
              "shared_entities": shared_entities(a_id, b_id)}))
}

pub fn taste(index: &Index, model: &TrailModel, req: &Value) -> Result<Value, String> {
    let mut score = [0.0f64; FAMILIES];
    for e in req.get("events").and_then(Value::as_array).map(Vec::as_slice).unwrap_or(&[]) {
        let (Some(id), Some(action)) = (e.get("verse_id").and_then(Value::as_i64), e.get("action").and_then(Value::as_str)) else {
            continue;
        };
        let Some(r) = index.row_of(id) else { continue };
        let s = match action {
            "like" => 1.0,
            "dislike" => -1.0,
            _ => continue,
        };
        for kk in 0..FAMILIES {
            score[kk] += s * (model.energy(r)[kk] - model.ebar[kk]);
        }
    }
    let mut order: Vec<usize> = (0..FAMILIES).collect();
    order.sort_by(|&a, &b| score[b].partial_cmp(&score[a]).unwrap().then(a.cmp(&b)));
    let families: Vec<Value> = order
        .into_iter()
        .filter(|&i| score[i] > 1e-9)
        .take(5)
        .map(|i| json!({"family": ((b'A' + i as u8) as char).to_string(), "score": score[i]}))
        .collect();
    Ok(json!({"mode": "taste", "families": families}))
}
