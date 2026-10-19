//! Semantic search over the stored indexes: dense, sparse and genome scans, 200-per-lane candidate union, ColBERT
//! MaxSim from the precomputed pack, z-score fusion. Mirrors tool/reference_search.py + tool/make_fusion_goldens.py.
//! Returns verse IDs and scores only (docs/ENGINE_PLAN.md section 3).

use crate::encoder::{Encoded, DIM};
use crate::kernels::{dot_rows_f16, dot_rows_f32, l2_normalize, top_k, zscore};
use crate::npy::Npy;
use half::f16;
use std::path::Path;

pub const LANE_K: usize = 200;
const SHARD_VERSES: usize = 1000;
const FAMILY_WEIGHTS: [(char, f32); 6] = [('B', 0.75), ('I', 0.50), ('N', 0.50), ('Q', 0.0), ('T', 0.75), ('U', 0.75)];

/// Signal weights of one search profile (Echo = dense, Spark = sparse, Thread = ColBERT, Root = genome).
#[derive(Clone, Copy, Debug)]
pub struct Weights {
    pub echo: f64,
    pub spark: f64,
    pub thread: f64,
    pub root: f64,
}

#[derive(Clone, Debug)]
pub struct Hit {
    pub verse_id: i64,
    pub score: f64,
    /// [dense, sparse, colbert, genome] z-scored lane values that `score` was fused from (docs: offline research
    /// reads these to combine them differently from the shipped fusion weights). Set only when requested.
    pub lanes: Option<[f64; 4]>,
    /// Keyword concentration (docs/ANSWER_FOCUS_KEYWORD_CONCENTRATION_PROTOCOL.md): the sparse lane's single
    /// largest per-term contribution divided by its total, in [0, 1]. Set only when requested, and only alongside
    /// `lanes` (concentration is reported next to the sparse lane it describes).
    pub concentration: Option<f64>,
}

#[derive(Debug)]
pub struct Outcome {
    pub hits: Vec<Hit>,
    pub candidates: usize,
}

struct Head {
    w0: Vec<f32>, // [4096, 1024]
    b0: Vec<f32>,
    w1: Vec<f32>, // [568, 4096]
    b1: Vec<f32>,
}

struct Csr {
    indptr: Vec<i32>,
    indices: Vec<i32>,
    data: Vec<f32>,
    vocab: usize,
}

pub struct Pack {
    vec: Vec<Npy>,
    cum: Vec<Vec<u64>>,
}

impl Pack {
    pub fn open(dir: impl AsRef<Path>) -> Result<Self, String> {
        let dir = dir.as_ref();
        let (mut vec, mut cum) = (Vec::new(), Vec::new());
        for i in 0.. {
            let v = dir.join(format!("shard-{i:04}.vec.npy"));
            if !v.exists() {
                break;
            }
            vec.push(Npy::open(&v)?);
            let counts = Npy::open(dir.join(format!("shard-{i:04}.cnt.npy")))?.to_i32()?;
            let mut c = Vec::with_capacity(counts.len() + 1);
            c.push(0u64);
            for n in counts {
                c.push(c.last().unwrap() + n as u64);
            }
            cum.push(c);
        }
        if vec.is_empty() {
            return Err(format!("no ColBERT shards in {}", dir.display()));
        }
        Ok(Self { vec, cum })
    }

    fn tokens(&self, row: usize) -> Result<&[u16], String> {
        let (sh, loc) = (row / SHARD_VERSES, row % SHARD_VERSES);
        let (lo, hi) = (self.cum[sh][loc] as usize, self.cum[sh][loc + 1] as usize);
        Ok(&self.vec[sh].f16_bits()?[lo * DIM..hi * DIM])
    }

    /// Mean over query tokens of the best dot product over the passage's tokens.
    fn maxsim(&self, q: &[f32], rows: &[usize], cancel: &dyn Fn() -> bool) -> Result<Vec<f64>, String> {
        let tq = q.len() / DIM;
        let mut out = Vec::with_capacity(rows.len());
        let mut scratch: Vec<f32> = Vec::new();
        for (n, &r) in rows.iter().enumerate() {
            if n % 32 == 0 && cancel() {
                return Err("cancelled".into());
            }
            let bits = self.tokens(r)?;
            scratch.clear();
            scratch.extend(bits.iter().map(|&b| f16::from_bits(b).to_f32()));
            let mut sum = 0f32;
            for t in 0..tq {
                let best = dot_rows_f32(&scratch, DIM, &q[t * DIM..(t + 1) * DIM]).into_iter().fold(f32::NEG_INFINITY, f32::max);
                sum += best;
            }
            out.push((sum / tq as f32) as f64);
        }
        Ok(out)
    }
}

pub struct Index {
    pub verse_ids: Vec<i64>,
    dense: Npy,
    genome: Vec<f32>, // [n, genes], rows L2-normalised
    genes: usize,
    sw: Vec<f32>,
    gene_ids: Vec<String>,
    csr: Csr,
    head: Head,
    pack: Option<Pack>,
}

fn gelu(x: f32) -> f32 {
    let x = x as f64;
    (0.5 * x * (1.0 + libm::erf(x / std::f64::consts::SQRT_2))) as f32
}

impl Index {
    /// `retrieval` = scripture-retrieval-english-v1 directory, `head` = head_fp16.npz, `pack` = optional ColBERT pack.
    pub fn open(retrieval: &Path, head: &Path, pack: Option<&Path>) -> Result<Self, String> {
        let verse_ids = Npy::open(retrieval.join("verse_ids.npy"))?.to_i64()?;
        let dense = Npy::open(retrieval.join("dense_embeddings.f16.npy"))?;
        let n = verse_ids.len();
        if dense.shape != [n, DIM] {
            return Err(format!("dense shape {:?} does not match {n} verses", dense.shape));
        }
        let g = Npy::open(retrieval.join("weighted_genome_embeddings.f16.npy"))?;
        let genes = g.shape[1];
        let mut genome = g.to_f32()?;
        genome.chunks_exact_mut(genes).for_each(l2_normalize);

        let gene_ids = std::fs::read_to_string(retrieval.join("gene_ids.txt")).map_err(|e| e.to_string())?;
        let gene_names: Vec<String> = gene_ids.lines().filter(|l| !l.is_empty()).map(String::from).collect();
        let sw: Vec<f32> = gene_ids
            .lines()
            .filter(|l| !l.is_empty())
            .map(|l| {
                let c = l.chars().next().unwrap();
                FAMILY_WEIGHTS.iter().find(|(f, _)| *f == c).map(|(_, w)| *w).unwrap_or(1.0).sqrt()
            })
            .collect();
        if sw.len() != genes {
            return Err(format!("{} genes in gene_ids.txt but {genes} in the genome matrix", sw.len()));
        }

        let sp = retrieval.join("sparse_index.csr.npz");
        let shape = Npy::from_npz(&sp, "shape.npy")?.to_i64()?;
        let csr = Csr {
            indptr: Npy::from_npz(&sp, "indptr.npy")?.to_i32()?,
            indices: Npy::from_npz(&sp, "indices.npy")?.to_i32()?,
            data: Npy::from_npz(&sp, "data.npy")?.to_f32()?,
            vocab: shape[1] as usize,
        };
        if csr.indptr.len() != n + 1 {
            return Err("sparse index rows do not match verse IDs".into());
        }
        let head = Head {
            w0: Npy::from_npz(head, "w0.npy")?.to_f32()?,
            b0: Npy::from_npz(head, "b0.npy")?.to_f32()?,
            w1: Npy::from_npz(head, "w1.npy")?.to_f32()?,
            b1: Npy::from_npz(head, "b1.npy")?.to_f32()?,
        };
        let pack = pack.map(Pack::open).transpose()?;
        Ok(Self { verse_ids, dense, genome, genes, sw, gene_ids: gene_names, csr, head, pack })
    }

    pub fn genes(&self) -> usize {
        self.genes
    }

    pub fn genome_row(&self, row: usize) -> &[f32] {
        &self.genome[row * self.genes..(row + 1) * self.genes]
    }

    pub fn genome_matrix(&self) -> &[f32] {
        &self.genome
    }

    pub fn sw(&self) -> &[f32] {
        &self.sw
    }

    pub fn gene_ids(&self) -> &[String] {
        &self.gene_ids
    }

    /// Predicted genome of an encoded query (family-weighted, unit length): the space the verse vectors live in.
    pub fn predicted_genome(&self, dense_q: &[f32]) -> Vec<f32> {
        self.query_genome(dense_q)
    }

    /// Sparse terms both verses carry: (token id, weight product), best first.
    pub fn shared_terms(&self, a: usize, b: usize, top: usize) -> Vec<(u32, f32)> {
        let row = |r: usize| -> std::collections::HashMap<u32, f32> {
            let (lo, hi) = (self.csr.indptr[r] as usize, self.csr.indptr[r + 1] as usize);
            (lo..hi).map(|k| (self.csr.indices[k] as u32, self.csr.data[k])).collect()
        };
        let (ra, rb) = (row(a), row(b));
        let mut shared: Vec<(u32, f32)> = ra.iter().filter_map(|(t, wa)| rb.get(t).map(|wb| (*t, wa * wb))).collect();
        shared.sort_by(|x, y| y.1.partial_cmp(&x.1).unwrap().then(x.0.cmp(&y.0)));
        shared.truncate(top);
        shared
    }

    pub fn row_of(&self, verse_id: i64) -> Option<usize> {
        self.verse_ids.binary_search(&verse_id).ok()
    }

    /// Eligibility mask from inclusive verse-ID ranges (what the catalog resolves book/chapter/canon filters to).
    pub fn mask_from_ranges(&self, ranges: &[(i64, i64)]) -> Vec<bool> {
        let mut m = vec![false; self.verse_ids.len()];
        for &(lo, hi) in ranges {
            let a = self.verse_ids.partition_point(|&v| v < lo);
            let b = self.verse_ids.partition_point(|&v| v <= hi);
            m[a..b].iter_mut().for_each(|x| *x = true);
        }
        m
    }

    /// Profile `genome_weighted_cosine_v1`: cosine over the stored family-weighted verse genomes. The source verse
    /// is excluded; ties by ascending verse ID; an eligibility mask is applied before ranking.
    pub fn similar(&self, verse_id: i64, top: usize, allowed: Option<&[bool]>) -> Result<Vec<Hit>, String> {
        let row = self.row_of(verse_id).ok_or_else(|| format!("unknown verse id {verse_id}"))?;
        let g = &self.genome[row * self.genes..(row + 1) * self.genes];
        let scores: Vec<f64> = dot_rows_f32(&self.genome, self.genes, g).into_iter().map(f64::from).collect();
        let cand: Vec<usize> = (0..scores.len()).filter(|&r| r != row && allowed.map_or(true, |m| m[r])).collect();
        Ok(top_k(&scores, &self.verse_ids, Some(&cand), top)
            .into_iter()
            .map(|r| Hit { verse_id: self.verse_ids[r], score: scores[r], lanes: None, concentration: None })
            .collect())
    }

    /// Genome cosine of `verse_id` against every verse (row order), plus the source's own row.
    pub fn genome_scores(&self, verse_id: i64) -> Result<(usize, Vec<f64>), String> {
        let row = self.row_of(verse_id).ok_or_else(|| format!("unknown verse id {verse_id}"))?;
        let g = &self.genome[row * self.genes..(row + 1) * self.genes];
        Ok((row, dot_rows_f32(&self.genome, self.genes, g).into_iter().map(f64::from).collect()))
    }

    pub fn has_pack(&self) -> bool {
        self.pack.is_some()
    }

    /// Predicted genome of a query: Linear -> exact GELU -> Linear -> Sigmoid, then family-weighted and normalised.
    fn query_genome(&self, dense_q: &[f32]) -> Vec<f32> {
        let h = &self.head;
        let mut x = dot_rows_f32(&h.w0, DIM, dense_q);
        for (v, b) in x.iter_mut().zip(&h.b0) {
            *v = gelu(*v + b);
        }
        let mut y = dot_rows_f32(&h.w1, x.len(), &x);
        for ((v, b), w) in y.iter_mut().zip(&h.b1).zip(&self.sw) {
            *v = (1.0 / (1.0 + (-(*v + b) as f64).exp())) as f32 * w;
        }
        l2_normalize(&mut y);
        y
    }

    /// Dense sparse-lane scores per row, also returning each row's keyword concentration: the single largest per-term
    /// contribution to the sum, divided by the sum (0 when the sum is <= 0 -- nothing to concentrate). A verse whose
    /// sparse score comes almost entirely from one shared word has concentration near 1; one that matches broadly
    /// across several terms has a lower value. Both are already computed per term inside this loop; only the sum
    /// survived before (docs/ANSWER_FOCUS_KEYWORD_CONCENTRATION_PROTOCOL.md).
    fn sparse_scores_with_concentration(&self, q: &[(u32, f32)]) -> (Vec<f64>, Vec<f64>) {
        let mut dense_q = vec![0f32; self.csr.vocab];
        for &(t, w) in q {
            dense_q[t as usize] = w;
        }
        let mut scores = Vec::with_capacity(self.verse_ids.len());
        let mut concentration = Vec::with_capacity(self.verse_ids.len());
        for r in 0..self.verse_ids.len() {
            let (lo, hi) = (self.csr.indptr[r] as usize, self.csr.indptr[r + 1] as usize);
            let mut s = 0f32;
            let mut best = 0f32;
            for k in lo..hi {
                let term = self.csr.data[k] * dense_q[self.csr.indices[k] as usize];
                s += term;
                best = best.max(term);
            }
            scores.push(s as f64);
            concentration.push(if s > 0.0 { (best / s) as f64 } else { 0.0 });
        }
        (scores, concentration)
    }

    /// `allowed`: per-row eligibility mask (None = whole corpus). Filtering happens before lane selection and
    /// before standardisation (docs/SEARCH_SPEC.md).
    pub fn search(
        &self,
        q: &Encoded,
        w: &Weights,
        top: usize,
        allowed: Option<&[bool]>,
        cancel: &dyn Fn() -> bool,
    ) -> Result<Outcome, String> {
        self.search_balanced(q, w, top, allowed, cancel, None, false, false)
    }

    /// As [`Index::search`], with the dense and genome lanes volume-balanced (crate::balance) before the per-lane
    /// candidate pick. Spark is left as it is: most rows score 0 there, and an offset would rank verses without the word
    /// above verses with it. Thread scores only the candidates and is left as it is too.
    ///
    /// `want_lanes`: set each hit's [`Hit::lanes`] to the four z-scored values `score` was fused from (offline
    /// research only; the shipped app never sets this). Costs only an allocation per candidate, no extra computation
    /// -- the lane values are already computed to build `score`.
    ///
    /// `want_concentration`: set each hit's [`Hit::concentration`] (docs/ANSWER_FOCUS_KEYWORD_CONCENTRATION_PROTOCOL.md).
    /// Ignored unless `want_lanes` is also set. Costs one extra running max per sparse-score term, already visited.
    #[allow(clippy::too_many_arguments)]
    pub fn search_balanced(
        &self,
        q: &Encoded,
        w: &Weights,
        top: usize,
        allowed: Option<&[bool]>,
        cancel: &dyn Fn() -> bool,
        balance: Option<(&crate::balance::Volumes, f64)>,
        want_lanes: bool,
        want_concentration: bool,
    ) -> Result<Outcome, String> {
        let eligible: Option<Vec<usize>> = allowed.map(|m| m.iter().enumerate().filter(|(_, &a)| a).map(|(i, _)| i).collect());
        if matches!(&eligible, Some(e) if e.is_empty()) {
            return Ok(Outcome { hits: Vec::new(), candidates: 0 });
        }
        let ids = &self.verse_ids;
        let mut da: Vec<f64> = dot_rows_f16(self.dense.f16_bits()?, DIM, &q.dense).into_iter().map(f64::from).collect();
        let mut ga: Vec<f64> = dot_rows_f32(&self.genome, self.genes, &self.query_genome(&q.dense)).into_iter().map(f64::from).collect();
        let (sa, conc) = self.sparse_scores_with_concentration(&q.sparse);
        if let Some((v, strength)) = balance {
            let ok = |r: usize| allowed.map_or(true, |m| m[r]);
            for lane in [&mut da, &mut ga] {
                v.balance(lane, &ok, strength, false);
            }
        }
        if cancel() {
            return Err("cancelled".into());
        }

        let lane = |s: &[f64]| top_k(s, ids, eligible.as_deref(), LANE_K);
        let mut cand: Vec<usize> = [lane(&da), lane(&sa), lane(&ga)].concat();
        cand.sort_unstable();
        cand.dedup();

        let zd = zscore(&cand.iter().map(|&r| da[r]).collect::<Vec<_>>());
        let zs = zscore(&cand.iter().map(|&r| sa[r]).collect::<Vec<_>>());
        let zg = zscore(&cand.iter().map(|&r| ga[r]).collect::<Vec<_>>());
        let zc = match (&self.pack, w.thread != 0.0) {
            (Some(p), true) => zscore(&p.maxsim(&q.colbert, &cand, cancel)?),
            (None, true) => return Err("this profile needs the ColBERT pack (Thread), which is not installed".into()),
            _ => vec![0.0; cand.len()],
        };
        let fused: Vec<f64> = (0..cand.len()).map(|i| w.echo * zd[i] + w.spark * zs[i] + w.thread * zc[i] + w.root * zg[i]).collect();
        let cand_ids: Vec<i64> = cand.iter().map(|&r| ids[r]).collect();
        let hits = top_k(&fused, &cand_ids, None, top)
            .into_iter()
            .map(|i| Hit {
                verse_id: cand_ids[i],
                score: fused[i],
                lanes: want_lanes.then_some([zd[i], zs[i], zc[i], zg[i]]),
                concentration: (want_lanes && want_concentration).then(|| conc[cand[i]]),
            })
            .collect();
        Ok(Outcome { hits, candidates: cand.len() })
    }
}
