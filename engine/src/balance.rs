//! Volume balance (docs/superpowers/plans/2026-10-14-volume-balance.md; reference: tool/volume_balance.py).
//! When two or more volumes are in scope, each volume's baseline for this request (the mean of its best TOP_FRAC eligible
//! scores) is partly removed before the volumes compete, so no volume wins only for being itself. One volume = no change.

use crate::search::Index;
use serde::Deserialize;

pub const TOP_FRAC: f64 = 0.03; // tool/volume_balance.py, chosen in Task 1 (re-measured after the review fixes)
/// A volume's baseline needs at least this many top scores; otherwise it takes the mean offset of the others.
pub const MIN_TOP: usize = 5;
const VOLUMES_JSON: &str = include_str!("../data/volumes.json");

#[derive(Deserialize)]
struct Range {
    first: i64,
    last: i64,
}

#[derive(Deserialize)]
struct File {
    volumes: Vec<Range>,
}

pub struct Volumes {
    of_row: Vec<u8>,
    count: usize,
}

impl Volumes {
    /// The embedded volume ranges, or None when a verse of the index falls outside them (balance is then off).
    pub fn open_embedded(index: &Index) -> Option<Self> {
        let f: File = serde_json::from_str(VOLUMES_JSON).ok()?;
        let mut of_row = Vec::with_capacity(index.verse_ids.len());
        for &v in &index.verse_ids {
            of_row.push(f.volumes.iter().position(|r| r.first <= v && v <= r.last)? as u8);
        }
        Some(Self::from_rows(of_row, f.volumes.len()))
    }

    pub fn from_rows(of_row: Vec<u8>, count: usize) -> Self {
        Self { of_row, count }
    }

    /// See the module doc; `eligible(row)` is the request's candidate set (filter, source verse excluded).
    /// `positive_only` for lanes where 0 means "no evidence" (topic overlap): rows at 0 stay 0, the others never fall below 0.
    pub fn balance(&self, s: &mut [f64], eligible: &dyn Fn(usize) -> bool, strength: f64, positive_only: bool) {
        self.balance_with(s, eligible, strength, TOP_FRAC, MIN_TOP, positive_only)
    }

    pub fn balance_with(
        &self,
        s: &mut [f64],
        eligible: &dyn Fn(usize) -> bool,
        strength: f64,
        top_frac: f64,
        min_top: usize,
        positive_only: bool,
    ) {
        if strength <= 0.0 {
            return;
        }
        let mut per: Vec<Vec<f64>> = vec![Vec::new(); self.count];
        for (r, &k) in self.of_row.iter().enumerate() {
            if eligible(r) {
                per[k as usize].push(s[r]);
            }
        }
        if per.iter().filter(|p| !p.is_empty()).count() < 2 {
            return;
        }
        let mut base: Vec<Option<f64>> = vec![None; self.count];
        for (k, p) in per.iter_mut().enumerate() {
            let n = ((top_frac * p.len() as f64).ceil() as usize).max(1);
            if !p.is_empty() && n >= min_top {
                let cut = p.len() - n;
                p.select_nth_unstable_by(cut, |a, b| a.partial_cmp(b).unwrap());
                base[k] = Some(p[cut..].iter().sum::<f64>() / n as f64);
            }
        }
        let got: Vec<f64> = base.iter().flatten().copied().collect();
        if got.is_empty() {
            return;
        }
        let fill = got.iter().sum::<f64>() / got.len() as f64;
        let off: Vec<f64> =
            (0..self.count).map(|k| if per[k].is_empty() { 0.0 } else { strength * base[k].unwrap_or(fill) }).collect();
        for (r, &k) in self.of_row.iter().enumerate() {
            if !positive_only {
                s[r] -= off[k as usize];
            } else if s[r] > 0.0 {
                s[r] = (s[r] - off[k as usize]).max(0.0);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 300 / 200 / 100 rows in volumes 0 / 1 / 2, scores in [0, 1) with volume 0 lifted by 0.5 (as test/volume_balance_check.py).
    fn fixture() -> (Volumes, Vec<f64>) {
        let of_row: Vec<u8> = (0..600).map(|r| if r < 300 { 0 } else if r < 500 { 1 } else { 2 }).collect();
        let mut x: u64 = 12345;
        let s = of_row
            .iter()
            .map(|&k| {
                x = x.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
                (x >> 11) as f64 / (1u64 << 53) as f64 + if k == 0 { 0.5 } else { 0.0 }
            })
            .collect();
        (Volumes::from_rows(of_row, 3), s)
    }

    fn top_share(v: &Volumes, s: &[f64], k: u8, n: usize) -> f64 {
        let mut order: Vec<usize> = (0..s.len()).collect();
        order.sort_by(|&a, &b| s[b].partial_cmp(&s[a]).unwrap());
        order[..n].iter().filter(|&&r| v.of_row[r] == k).count() as f64 / n as f64
    }

    #[test]
    fn strength_zero_changes_nothing() {
        let (v, s) = fixture();
        let mut b = s.clone();
        v.balance_with(&mut b, &|_| true, 0.0, 0.05, 5, false);
        assert_eq!(b, s);
    }

    #[test]
    fn one_volume_in_scope_changes_nothing() {
        let (v, s) = fixture();
        let mut b = s.clone();
        v.balance_with(&mut b, &|r| (300..500).contains(&r), 0.5, 0.05, 5, false);
        assert_eq!(b, s);
    }

    #[test]
    fn the_inflated_volume_loses_share() {
        let (v, s) = fixture();
        let mut b = s.clone();
        v.balance_with(&mut b, &|_| true, 1.0, 0.05, 5, false);
        assert!(top_share(&v, &s, 0, 30) >= 0.8 && top_share(&v, &b, 0, 30) < 0.8);
    }

    #[test]
    fn order_inside_a_volume_is_kept() {
        let (v, s) = fixture();
        let mut b = s.clone();
        v.balance_with(&mut b, &|_| true, 0.5, 0.05, 5, false);
        let d: Vec<f64> = (0..300).map(|r| s[r] - b[r]).collect();
        assert!(d.iter().all(|x| (x - d[0]).abs() < 1e-12), "one offset per volume");
    }

    #[test]
    fn a_small_part_takes_the_mean_offset() {
        let (v, s) = fixture();
        let mut b = s.clone();
        v.balance_with(&mut b, &|r| r < 505, 0.5, 0.05, 5, false); // volume 2 touched by five rows only
        let d = |r: usize| s[r] - b[r];
        assert!((d(500) - (d(0) + d(300)) / 2.0).abs() < 1e-12);
    }

    #[test]
    fn a_part_with_too_few_top_scores_takes_the_mean_offset() {
        let (v, s) = fixture();
        let mut b = s.clone();
        v.balance_with(&mut b, &|r| r < 580, 0.5, 0.005, 5, false); // 80 rows of volume 2: ceil(0.005 * 80) = 1 < 5
        let d = |r: usize| s[r] - b[r];
        assert!((d(500) - (d(0) + d(300)) / 2.0).abs() < 1e-12);
    }

    #[test]
    fn positive_only_keeps_no_evidence_at_zero_and_evidence_above_it() {
        let (v, s) = fixture();
        let t: Vec<f64> = s.iter().enumerate().map(|(r, &x)| if r % 5 == 0 { x * 3.0 } else { 0.0 }).collect();
        let mut b = t.clone();
        v.balance_with(&mut b, &|_| true, 0.75, 0.05, 5, true);
        assert!(t.iter().zip(&b).all(|(&a, &x)| if a == 0.0 { x == 0.0 } else { x >= 0.0 }));
        assert!(t.iter().zip(&b).any(|(&a, &x)| a > 0.0 && x < a), "evidence rows are still balanced");
    }
}
