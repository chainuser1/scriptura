//! BGE-M3 query encoder through ONNX Runtime (CPU). One query per call, no padding, so the outputs match the
//! batch-1 Python reference (test/golden/encoder_*.json).

use ort::environment::Environment;
use ort::session::{builder::GraphOptimizationLevel, Session};
use ort::value::Tensor;
use std::path::Path;
use std::sync::OnceLock;

pub const DIM: usize = 1024;
/// <s>, <pad>, </s>, <unk>: never contribute sparse weight.
const SPECIAL_IDS: [u32; 4] = [0, 1, 2, 3];

pub struct Encoded {
    pub dense: Vec<f32>,
    /// (token id, weight), ascending token id, weights > 0, max over repeated tokens.
    pub sparse: Vec<(u32, f32)>,
    /// Row-major [rows, DIM]; the CLS row is already dropped by the graph, matching the stored passage index.
    pub colbert: Vec<f32>,
    pub rows: usize,
}

pub struct Encoder {
    session: Session,
}

fn err<E: std::fmt::Display>(e: E) -> String {
    e.to_string()
}

/// ONNX Runtime allows one environment per process.
pub(crate) fn environment() -> Result<&'static Environment, String> {
    static ENV: OnceLock<Result<Environment, String>> = OnceLock::new();
    ENV.get_or_init(build_environment).as_ref().map_err(|e| e.clone())
}

/// Library to load when ONNX Runtime is not linked in (feature `dynamic-ort`); set before the first `Encoder::open`.
pub fn set_ort_library(path: impl Into<String>) {
    let _ = ORT_LIBRARY.set(path.into());
}

static ORT_LIBRARY: OnceLock<String> = OnceLock::new();

#[cfg(feature = "dynamic-ort")]
fn build_environment() -> Result<Environment, String> {
    let lib = ORT_LIBRARY.get().map(String::as_str).unwrap_or("libonnxruntime.so");
    ort::init_from(lib).map_err(err)?.with_name("scripture_engine").build().map_err(err)
}

#[cfg(not(feature = "dynamic-ort"))]
fn build_environment() -> Result<Environment, String> {
    ort::init().with_name("scripture_engine").build().map_err(err)
}

impl Encoder {
    pub fn open(model: impl AsRef<Path>, threads: usize) -> Result<Self, String> {
        let session = Session::builder(environment()?)
            .map_err(err)?
            .with_optimization_level(GraphOptimizationLevel::Level3)
            .map_err(err)?
            .with_intra_threads(threads)
            .map_err(err)?
            .commit_from_file(model.as_ref())
            .map_err(err)?;
        Ok(Self { session })
    }

    pub fn encode(&mut self, ids: &[u32]) -> Result<Encoded, String> {
        let n = ids.len();
        let input_ids = Tensor::from_array(([1usize, n], ids.iter().map(|&x| x as i64).collect::<Vec<_>>())).map_err(err)?;
        let mask = Tensor::from_array(([1usize, n], vec![1i64; n])).map_err(err)?;
        let outputs = self
            .session
            .run(ort::inputs!["input_ids" => input_ids, "attention_mask" => mask])
            .map_err(err)?;
        let (_, dense) = outputs[0].try_extract_tensor::<f32>().map_err(err)?;
        let (_, weights) = outputs[1].try_extract_tensor::<f32>().map_err(err)?;
        let (_, colbert) = outputs[2].try_extract_tensor::<f32>().map_err(err)?;
        if dense.len() != DIM || weights.len() != n || colbert.len() != (n - 1) * DIM {
            return Err(format!("unexpected output sizes: dense {} weights {} colbert {}", dense.len(), weights.len(), colbert.len()));
        }
        let mut sparse: Vec<(u32, f32)> = Vec::new();
        for (&t, &w) in ids.iter().zip(weights.iter()) {
            if SPECIAL_IDS.contains(&t) || w <= 0.0 {
                continue;
            }
            match sparse.iter_mut().find(|(k, _)| *k == t) {
                Some(e) => e.1 = e.1.max(w),
                None => sparse.push((t, w)),
            }
        }
        sparse.sort_by_key(|(k, _)| *k);
        // the graph already drops the CLS row: n tokens in, n - 1 ColBERT rows out
        Ok(Encoded { dense: dense.to_vec(), sparse, colbert: colbert.to_vec(), rows: n - 1 })
    }
}
