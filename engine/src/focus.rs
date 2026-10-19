//! Answer focus: a cross-encoder (BAAI/bge-reranker-v2-m3 as ONNX) that scores how well each passage answers a question.
//! Text comes in with the request and is not kept. Runs on the graphics chip through DirectML when asked and available
//! (Windows), otherwise on the CPU. Scores are raw logits: comparable within one request, not a probability.

use crate::encoder::environment;
use ort::session::{builder::GraphOptimizationLevel, Session};
use ort::value::Tensor;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::OnceLock;
use tokenizers::{Tokenizer, TruncationParams};

/// The model's input limit (question and passage together), as in training and in tool/reranker_stage2.py.
const MAX_TOKENS: usize = 512;
/// Pairs per run on the graphics chip. On the CPU each pair runs alone: the int8 model quantizes activations per run,
/// so batching makes a score depend on its neighbours (and pads short verses); one at a time is stable and was faster
/// (1.27 s against 1.96 s for 10 passages on the reference laptop).
const GPU_BATCH: usize = 10;
const PAD_ID: u32 = 1;

/// Which reranker model this [Focus] was opened for, since each tokenizes its input differently.
#[derive(Clone, Copy, PartialEq, Eq)]
pub enum RerankerFamily {
    /// BAAI/bge-reranker-v2-m3: a tokenizer pair `(query, text)`.
    Ezra,
    /// nvidia/llama-nemotron-rerank-1b-v2: one concatenated string.
    Apollos,
}

pub struct Focus {
    session: Session,
    tok: Tokenizer,
    gpu: bool,
    model: PathBuf,
    threads: usize,
    family: RerankerFamily,
}

fn err<E: std::fmt::Display>(e: E) -> String {
    e.to_string()
}

/// True when this build of ONNX Runtime has DirectML and a graphics device runs a tiny model with it. Probed once.
pub fn gpu_available() -> bool {
    static GPU: OnceLock<bool> = OnceLock::new();
    *GPU.get_or_init(|| probe().is_ok())
}

#[cfg(not(windows))]
fn probe() -> Result<(), String> {
    Err("no DirectML on this platform".into())
}

#[cfg(not(windows))]
fn dml_session_builder() -> Result<ort::session::builder::SessionBuilder, String> {
    Err("no DirectML on this platform".into())
}

#[cfg(windows)]
fn probe() -> Result<(), String> {
    let mut s = dml_session_builder()?.commit_from_memory(include_bytes!("../data/dml_probe.onnx")).map_err(err)?;
    let x = Tensor::from_array(([1usize], vec![1.0f32])).map_err(err)?;
    let out = s.run(ort::inputs!["x" => x]).map_err(err)?;
    let (_, y) = out[0].try_extract_tensor::<f32>().map_err(err)?;
    if y == [2.0] { Ok(()) } else { Err(format!("probe returned {y:?}")) }
}

#[cfg(windows)]
fn dml_session_builder() -> Result<ort::session::builder::SessionBuilder, String> {
    use ort::ep::DirectML;
    ort::ep::directml::api().ok_or("DirectML is not in this build")?;
    Session::builder(environment()?)
        .map_err(err)?
        .with_memory_pattern(false) // DirectML requires both of these
        .map_err(err)?
        .with_parallel_execution(false)
        .map_err(err)?
        .with_execution_providers([DirectML::default().build().error_on_failure()])
        .map_err(err)
}

impl Focus {
    /// Opens the model on the graphics chip when [want_gpu] and it works, else on the CPU.
    pub fn open(model: &Path, tokenizer: &Path, threads: usize, want_gpu: bool, family: RerankerFamily) -> Result<Self, String> {
        let mut tok = Tokenizer::from_file(tokenizer).map_err(err)?;
        tok.with_truncation(Some(TruncationParams { max_length: MAX_TOKENS, ..Default::default() })).map_err(err)?;
        tok.with_padding(None);
        let (model, threads) = (model.to_path_buf(), threads.max(1));
        if want_gpu && gpu_available() {
            if let Ok(session) = dml_session_builder().and_then(|b| b.with_optimization_level(GraphOptimizationLevel::Level3).map_err(err)).and_then(|mut b| b.commit_from_file(&model).map_err(err)) {
                return Ok(Self { session, tok, gpu: true, model, threads, family });
            }
        }
        let session = cpu_session(&model, threads)?;
        Ok(Self { session, tok, gpu: false, model, threads, family })
    }

    /// Moves the model to the CPU for good (a graphics failure at run time: driver reset, device removed).
    pub fn fall_back_to_cpu(&mut self) -> Result<(), String> {
        self.session = cpu_session(&self.model, self.threads)?;
        self.gpu = false;
        Ok(())
    }

    pub fn device(&self) -> &'static str {
        if self.gpu { "gpu" } else { "cpu" }
    }

    /// Token ids for one (query, text) pair, tokenized the way [self.family] expects: Ezra as a tokenizer pair
    /// (`<s> q </s></s> p </s>`), Apollos as one concatenated string. Truncated to the model limit either way.
    pub fn encode(&self, query: &str, text: &str) -> Result<Vec<u32>, String> {
        match self.family {
            RerankerFamily::Ezra => Ok(self.tok.encode((query, text), true).map_err(err)?.get_ids().to_vec()),
            RerankerFamily::Apollos => {
                let s = format!("question:{query} \n \n passage:{text}");
                Ok(self.tok.encode(s, true).map_err(err)?.get_ids().to_vec())
            }
        }
    }

    /// Tokenizes a single string with no query/passage formatting. Test-only in intent (lets tests verify
    /// [Self::encode]'s Apollos formatting independently, without duplicating that formatting in the test itself),
    /// but not `#[cfg(test)]`: `engine/tests/focus_e2e.rs` is a separate crate and links the library with that cfg
    /// off, so a cfg-gated method would not be visible there.
    pub fn tokenizer_encode_single(&self, s: &str) -> Result<Vec<u32>, String> {
        Ok(self.tok.encode(s, true).map_err(err)?.get_ids().to_vec())
    }

    /// One score per text, in order. Checks [cancel] between batches. A graphics failure moves to the CPU and retries.
    pub fn score(&mut self, query: &str, texts: &[&str], cancel: &AtomicBool) -> Result<Vec<f32>, String> {
        match self.score_on_device(query, texts, cancel) {
            Err(e) if self.gpu && e != "cancelled" => {
                self.fall_back_to_cpu()?;
                self.score_on_device(query, texts, cancel)
            }
            r => r,
        }
    }

    /// Pairs per run: [GPU_BATCH] only for Ezra on the graphics chip. The Apollos packs are exported with a fixed
    /// batch dimension of 1 (`input_ids [1, seq_len]`, manifest `batch_size: 1`), so Apollos always runs one at a time.
    fn batch(&self) -> usize {
        if self.gpu && self.family == RerankerFamily::Ezra { GPU_BATCH } else { 1 }
    }

    fn score_on_device(&mut self, query: &str, texts: &[&str], cancel: &AtomicBool) -> Result<Vec<f32>, String> {
        let mut out = Vec::with_capacity(texts.len());
        for chunk in texts.chunks(self.batch()) {
            if cancel.load(Ordering::SeqCst) {
                return Err("cancelled".into());
            }
            let pairs: Vec<Vec<u32>> = chunk.iter().map(|t| self.encode(query, t)).collect::<Result<_, _>>()?;
            let width = pairs.iter().map(Vec::len).max().unwrap_or(0);
            let (mut ids, mut mask) = (Vec::with_capacity(chunk.len() * width), Vec::with_capacity(chunk.len() * width));
            for p in &pairs {
                ids.extend(p.iter().map(|&x| x as i64).chain(std::iter::repeat(PAD_ID as i64).take(width - p.len())));
                mask.extend(std::iter::repeat(1i64).take(p.len()).chain(std::iter::repeat(0).take(width - p.len())));
            }
            let shape = [chunk.len(), width];
            let input_ids = Tensor::from_array((shape, ids)).map_err(err)?;
            let attention = Tensor::from_array((shape, mask)).map_err(err)?;
            let outputs = self.session.run(ort::inputs!["input_ids" => input_ids, "attention_mask" => attention]).map_err(err)?;
            let (_, logits) = outputs[0].try_extract_tensor::<f32>().map_err(err)?;
            if logits.len() != chunk.len() {
                return Err(format!("expected {} scores, got {}", chunk.len(), logits.len()));
            }
            out.extend_from_slice(logits);
        }
        Ok(out)
    }
}

fn cpu_session(model: &Path, threads: usize) -> Result<Session, String> {
    Session::builder(environment()?)
        .map_err(err)?
        .with_optimization_level(GraphOptimizationLevel::Level3)
        .map_err(err)?
        .with_intra_threads(threads)
        .map_err(err)?
        .commit_from_file(model)
        .map_err(err)
}
