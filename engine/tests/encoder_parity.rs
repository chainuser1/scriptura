//! Gate E1: Rust encoder output versus the Python ONNX Runtime reference for the same INT8 graph
//! (test/golden/encoder_matmul.json from tool/make_encoder_goldens.py).
//! Needs generated-artifacts/onnx-int8 and the pinned tokenizer; skipped when absent.

use scripture_engine::{encoder::Encoder, tokenizer::QueryTokenizer};
use std::path::PathBuf;

fn root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).parent().unwrap().to_path_buf()
}

fn cosine(a: &[f32], b: &[f32]) -> f64 {
    let (mut d, mut na, mut nb) = (0f64, 0f64, 0f64);
    for (x, y) in a.iter().zip(b) {
        d += (*x as f64) * (*y as f64);
        na += (*x as f64).powi(2);
        nb += (*y as f64).powi(2);
    }
    d / (na.sqrt() * nb.sqrt())
}

#[test]
fn encoder_matches_python_reference() {
    let model = root().join("generated-artifacts/onnx-int8/bge_m3_multi_int8_matmul.onnx");
    let tokj = root().join(".artifact-staging/import-application-v1/extracted/bge-m3-pinned/tokenizer.json");
    if !model.exists() || !tokj.exists() {
        eprintln!("skipped: model or tokenizer not present");
        return;
    }
    let golden: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(root().join("test/golden/encoder_matmul.json")).unwrap()).unwrap();
    let tok = QueryTokenizer::from_file(&tokj).unwrap();
    let mut enc = Encoder::open(&model, 1).unwrap();
    let mut report = Vec::new();
    for c in golden["cases"].as_array().unwrap() {
        let text = c["text"].as_str().unwrap();
        let ids = tok.encode(text).unwrap();
        let want_ids: Vec<u32> = c["ids"].as_array().unwrap().iter().map(|v| v.as_u64().unwrap() as u32).collect();
        assert_eq!(ids, want_ids, "tokenizer drift for {text:?}");
        let got = enc.encode(&ids).unwrap();

        let dense: Vec<f32> = c["dense"].as_array().unwrap().iter().map(|v| v.as_f64().unwrap() as f32).collect();
        let dense_cos = cosine(&got.dense, &dense);

        let want_sparse: Vec<(u32, f32)> = c["sparse"].as_object().unwrap().iter()
            .map(|(k, v)| (k.parse().unwrap(), v.as_f64().unwrap() as f32)).collect();
        let mut ws = want_sparse.clone();
        ws.sort_by_key(|(k, _)| *k);
        let same_tokens = ws.iter().map(|x| x.0).collect::<Vec<_>>() == got.sparse.iter().map(|x| x.0).collect::<Vec<_>>();
        let max_w = ws.iter().zip(&got.sparse).map(|(a, b)| (a.1 - b.1).abs()).fold(0f32, f32::max);

        let rows = c["colbert_rows"].as_u64().unwrap() as usize;
        assert_eq!(got.rows, rows, "colbert rows for {text:?}");
        let col: Vec<f32> = c["colbert"].as_array().unwrap().iter().map(|v| v.as_f64().unwrap() as f32).collect();
        let min_tok_cos = (0..rows).map(|r| cosine(&got.colbert[r * 1024..(r + 1) * 1024], &col[r * 1024..(r + 1) * 1024]))
            .fold(1f64, f64::min);

        report.push(format!("{text:?}: dense cos {dense_cos:.6} sparse same={same_tokens} max|dw|={max_w:.5} colbert min cos {min_tok_cos:.6}"));
        assert!(dense_cos >= 0.9999, "{text:?} dense cos {dense_cos}");
        assert!(same_tokens, "{text:?} sparse token sets differ");
        assert!(max_w < 1e-3, "{text:?} sparse weight diff {max_w}");
        assert!(min_tok_cos >= 0.999, "{text:?} colbert cos {min_tok_cos}");
    }
    println!("{}", report.join("
"));
}
