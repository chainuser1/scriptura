//! scripture_engine: tokenizer, kernels and fusion for the offline scripture reader.
//! Milestone E1 builds this up in parity-gated steps (docs/ENGINE_PLAN.md section 4).

pub mod capi;
pub mod encoder;
pub mod engine;
pub mod entities;
pub mod focus;
pub mod identity;
pub mod kernels;
pub mod npy;
pub mod phrase;
pub mod reference;
pub mod balance;
pub mod search;
pub mod tokenizer;
pub mod trails;
pub mod topics;
pub mod unpack;
