//! BGE-M3 (XLM-RoBERTa) tokenizer from the pinned `tokenizer.json`, via the official Hugging Face core so token IDs
//! match the Python goldens by construction. No truncation here: callers apply the model's length limit.

use std::path::Path;
use tokenizers::Tokenizer;

pub struct QueryTokenizer {
    inner: Tokenizer,
}

impl QueryTokenizer {
    pub fn from_file(path: impl AsRef<Path>) -> Result<Self, String> {
        let inner = Tokenizer::from_file(path.as_ref()).map_err(|e| e.to_string())?;
        Ok(Self { inner })
    }

    /// The token piece for an id (word starts carry the leading `\u{2581}`).
    pub fn piece(&self, id: u32) -> Option<String> {
        self.inner.id_to_token(id)
    }

    /// Token IDs including `<s>` and `</s>`.
    pub fn encode(&self, text: &str) -> Result<Vec<u32>, String> {
        let enc = self.inner.encode(text, true).map_err(|e| e.to_string())?;
        Ok(enc.get_ids().to_vec())
    }
}
