//! Streams a downloaded `.zip` pack onto disk. Exposed through the C ABI (`se_extract_zip`) so the app does not have to
//! inflate gigabytes in Dart. Entries are written under `out_dir` with the single top-level folder stripped, and any
//! entry that would escape `out_dir` is rejected.

use std::fs::{self, File};
use std::io::{self, BufWriter};
use std::path::{Component, Path, PathBuf};

/// Returns (files, bytes) extracted.
pub fn extract(zip_path: &Path, out_dir: &Path) -> Result<(u64, u64), String> {
    let f = File::open(zip_path).map_err(|e| format!("{}: {e}", zip_path.display()))?;
    let mut z = zip::ZipArchive::new(io::BufReader::new(f)).map_err(|e| format!("not a zip archive: {e}"))?;
    let (mut files, mut bytes) = (0u64, 0u64);
    for i in 0..z.len() {
        let mut entry = z.by_index(i).map_err(|e| e.to_string())?;
        let Some(rel) = entry.enclosed_name() else {
            return Err(format!("unsafe path in archive entry {i}"));
        };
        // drop the top-level folder the packer added (`<pack-id>/...`)
        let mut parts = rel.components().filter(|c| matches!(c, Component::Normal(_)));
        parts.next();
        let inner: PathBuf = parts.collect();
        if inner.as_os_str().is_empty() {
            continue;
        }
        let dest = out_dir.join(&inner);
        if entry.is_dir() {
            fs::create_dir_all(&dest).map_err(|e| e.to_string())?;
            continue;
        }
        if let Some(p) = dest.parent() {
            fs::create_dir_all(p).map_err(|e| e.to_string())?;
        }
        let mut w = BufWriter::with_capacity(1 << 20, File::create(&dest).map_err(|e| format!("{}: {e}", dest.display()))?);
        bytes += io::copy(&mut entry, &mut w).map_err(|e| format!("{}: {e}", inner.display()))?;
        files += 1;
    }
    Ok((files, bytes))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    fn make(path: &Path, entries: &[(&str, &[u8])]) {
        let mut w = zip::ZipWriter::new(File::create(path).unwrap());
        let opts = zip::write::SimpleFileOptions::default();
        for (name, data) in entries {
            w.start_file(*name, opts).unwrap();
            w.write_all(data).unwrap();
        }
        w.finish().unwrap();
    }

    #[test]
    fn strips_top_folder_and_writes_nested_files() {
        let d = std::env::temp_dir().join(format!("unpack-{}", std::process::id()));
        let _ = fs::remove_dir_all(&d);
        fs::create_dir_all(&d).unwrap();
        make(&d.join("p.zip"), &[("pack-v1/manifest.json", b"{}"), ("pack-v1/retrieval/a.npy", b"1234")]);
        let (files, bytes) = extract(&d.join("p.zip"), &d.join("out")).unwrap();
        assert_eq!((files, bytes), (2, 6));
        assert_eq!(fs::read(d.join("out/retrieval/a.npy")).unwrap(), b"1234");
        assert!(extract(&d.join("missing.zip"), &d.join("o2")).is_err());
        make(&d.join("bad.zip"), &[("x/../../escape.txt", b"no")]);
        assert!(extract(&d.join("bad.zip"), &d.join("o3")).is_err());
        assert!(!d.join("escape.txt").exists());
        fs::remove_dir_all(&d).unwrap();
    }
}
