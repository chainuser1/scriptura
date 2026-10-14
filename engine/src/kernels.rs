//! Deterministic numeric kernels. Everything that orders results uses (score descending, verse ID ascending), so a
//! tie never depends on thread count, build or platform.

use half::f16;
use std::cmp::Ordering;

/// Dot products of `rows` rows of a row-major f16 matrix (`dim` columns) with an f32 vector.
pub fn dot_rows_f16(mat: &[u16], dim: usize, q: &[f32]) -> Vec<f32> {
    debug_assert_eq!(q.len(), dim);
    mat.chunks_exact(dim)
        .map(|row| {
            let mut acc = [0f32; 8];
            for (r, qq) in row.chunks_exact(8).zip(q.chunks_exact(8)) {
                for i in 0..8 {
                    acc[i] += f16::from_bits(r[i]).to_f32() * qq[i];
                }
            }
            acc.iter().sum()
        })
        .collect()
}

pub fn dot_rows_f32(mat: &[f32], dim: usize, q: &[f32]) -> Vec<f32> {
    mat.chunks_exact(dim)
        .map(|row| {
            let mut acc = [0f32; 8];
            for (r, qq) in row.chunks_exact(8).zip(q.chunks_exact(8)) {
                for i in 0..8 {
                    acc[i] += r[i] * qq[i];
                }
            }
            acc.iter().sum::<f32>() + row.chunks_exact(8).remainder().iter().zip(q.chunks_exact(8).remainder()).map(|(a, b)| a * b).sum::<f32>()
        })
        .collect()
}

pub fn l2_normalize(v: &mut [f32]) {
    let n = v.iter().map(|x| (*x as f64) * (*x as f64)).sum::<f64>().sqrt().max(1e-12) as f32;
    v.iter_mut().for_each(|x| *x /= n);
}

fn cmp_desc(scores: &[f64], ids: &[i64], a: usize, b: usize) -> Ordering {
    scores[b].partial_cmp(&scores[a]).unwrap_or(Ordering::Equal).then(ids[a].cmp(&ids[b]))
}

/// Indices of the `k` best entries among `candidates` (all rows when `None`), best first.
pub fn top_k(scores: &[f64], ids: &[i64], candidates: Option<&[usize]>, k: usize) -> Vec<usize> {
    let mut idx: Vec<usize> = match candidates {
        Some(c) => c.to_vec(),
        None => (0..scores.len()).collect(),
    };
    let k = k.min(idx.len());
    if k == 0 {
        return Vec::new();
    }
    if k < idx.len() {
        idx.select_nth_unstable_by(k - 1, |&a, &b| cmp_desc(scores, ids, a, b));
        idx.truncate(k);
    }
    idx.sort_by(|&a, &b| cmp_desc(scores, ids, a, b));
    idx
}

/// Sample z-score (ddof = 1); all zeros when fewer than two values or no spread.
pub fn zscore(v: &[f64]) -> Vec<f64> {
    let n = v.len();
    if n < 2 {
        return vec![0.0; n];
    }
    let mean = v.iter().sum::<f64>() / n as f64;
    let var = v.iter().map(|x| (x - mean) * (x - mean)).sum::<f64>() / (n as f64 - 1.0);
    let sd = var.sqrt();
    if sd <= 1e-12 {
        return vec![0.0; n];
    }
    v.iter().map(|x| (x - mean) / sd).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ties_resolve_by_ascending_verse_id() {
        let scores = [1.0, 2.0, 2.0, 0.5];
        let ids = [40, 30, 10, 20];
        assert_eq!(top_k(&scores, &ids, None, 3), vec![2, 1, 0]);
    }

    #[test]
    fn candidate_subset_is_respected() {
        let scores = [9.0, 1.0, 2.0];
        let ids = [1, 2, 3];
        assert_eq!(top_k(&scores, &ids, Some(&[1, 2]), 5), vec![2, 1]);
    }

    #[test]
    fn zscore_handles_degenerate_input() {
        assert_eq!(zscore(&[3.0]), vec![0.0]);
        assert_eq!(zscore(&[2.0, 2.0, 2.0]), vec![0.0; 3]);
        let z = zscore(&[1.0, 2.0, 3.0]);
        assert!((z[0] + 1.0).abs() < 1e-12 && z[1].abs() < 1e-12 && (z[2] - 1.0).abs() < 1e-12);
    }
}
