//! Minimal NumPy `.npy` reader (versions 1-3, little-endian, C order) over a memory map or an owned buffer, plus
//! `.npz` member access. Only what the shipped indexes use: f16, f32, i32, i64.

use memmap2::Mmap;
use std::fs::File;
use std::io::Read;
use std::path::Path;

enum Backing {
    Map(Mmap),
    Owned(Vec<u8>),
}

pub struct Npy {
    backing: Backing,
    data_off: usize,
    pub descr: String,
    pub shape: Vec<usize>,
}

fn parse_header(b: &[u8]) -> Result<(String, Vec<usize>, usize), String> {
    if b.len() < 10 || &b[..6] != b"\x93NUMPY" {
        return Err("not an npy file".into());
    }
    let (hlen, start) = match b[6] {
        1 => (u16::from_le_bytes([b[8], b[9]]) as usize, 10),
        2 | 3 => (u32::from_le_bytes([b[8], b[9], b[10], b[11]]) as usize, 12),
        v => return Err(format!("unsupported npy version {v}")),
    };
    let header = std::str::from_utf8(b.get(start..start + hlen).ok_or("truncated npy header")?).map_err(|e| e.to_string())?;
    if header.contains("'fortran_order': True") {
        return Err("fortran order not supported".into());
    }
    let descr = header
        .split("'descr':")
        .nth(1)
        .and_then(|s| s.split('\'').nth(1))
        .ok_or("no descr")?
        .to_string();
    let shape_txt = header.split("'shape':").nth(1).and_then(|s| s.split('(').nth(1)).and_then(|s| s.split(')').next()).ok_or("no shape")?;
    let shape = shape_txt
        .split(',')
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(|s| s.parse::<usize>().map_err(|e| e.to_string()))
        .collect::<Result<Vec<_>, _>>()?;
    Ok((descr, shape, start + hlen))
}

impl Npy {
    pub fn open(path: impl AsRef<Path>) -> Result<Self, String> {
        let f = File::open(path.as_ref()).map_err(|e| format!("{}: {e}", path.as_ref().display()))?;
        // SAFETY: read-only map of a file the engine does not modify while mapped.
        let map = unsafe { Mmap::map(&f) }.map_err(|e| e.to_string())?;
        let (descr, shape, data_off) = parse_header(&map)?;
        Ok(Self { backing: Backing::Map(map), data_off, descr, shape })
    }

    pub fn from_bytes(bytes: Vec<u8>) -> Result<Self, String> {
        let (descr, shape, data_off) = parse_header(&bytes)?;
        Ok(Self { backing: Backing::Owned(bytes), data_off, descr, shape })
    }

    /// Member `name` (e.g. "indices.npy") of an `.npz` archive, read into memory.
    pub fn from_npz(path: impl AsRef<Path>, name: &str) -> Result<Self, String> {
        let f = File::open(path.as_ref()).map_err(|e| format!("{}: {e}", path.as_ref().display()))?;
        let mut z = zip::ZipArchive::new(f).map_err(|e| e.to_string())?;
        let mut m = z.by_name(name).map_err(|e| format!("{name}: {e}"))?;
        let mut buf = Vec::with_capacity(m.size() as usize);
        m.read_to_end(&mut buf).map_err(|e| e.to_string())?;
        Self::from_bytes(buf)
    }

    fn bytes(&self) -> &[u8] {
        let all: &[u8] = match &self.backing {
            Backing::Map(m) => m,
            Backing::Owned(v) => v,
        };
        &all[self.data_off..]
    }

    fn expect(&self, descr: &[&str]) -> Result<(), String> {
        if descr.contains(&self.descr.as_str()) {
            Ok(())
        } else {
            Err(format!("dtype {} not one of {:?}", self.descr, descr))
        }
    }

    pub fn len(&self) -> usize {
        self.shape.iter().product()
    }

    /// Raw f16 bit patterns, zero-copy when the map is 2-byte aligned (it is: headers are 64-byte padded).
    pub fn f16_bits(&self) -> Result<&[u16], String> {
        self.expect(&["<f2"])?;
        bytemuck::try_cast_slice(&self.bytes()[..self.len() * 2]).map_err(|e| format!("f16 view: {e}"))
    }

    pub fn to_f32(&self) -> Result<Vec<f32>, String> {
        let b = self.bytes();
        match self.descr.as_str() {
            "<f4" => Ok(b[..self.len() * 4].chunks_exact(4).map(|c| f32::from_le_bytes([c[0], c[1], c[2], c[3]])).collect()),
            "<f2" => Ok(b[..self.len() * 2]
                .chunks_exact(2)
                .map(|c| half::f16::from_bits(u16::from_le_bytes([c[0], c[1]])).to_f32())
                .collect()),
            d => Err(format!("cannot read {d} as f32")),
        }
    }

    pub fn to_i32(&self) -> Result<Vec<i32>, String> {
        self.expect(&["<i4"])?;
        Ok(self.bytes()[..self.len() * 4].chunks_exact(4).map(|c| i32::from_le_bytes([c[0], c[1], c[2], c[3]])).collect())
    }

    pub fn to_i64(&self) -> Result<Vec<i64>, String> {
        self.expect(&["<i8"])?;
        Ok(self.bytes()[..self.len() * 8]
            .chunks_exact(8)
            .map(|c| i64::from_le_bytes([c[0], c[1], c[2], c[3], c[4], c[5], c[6], c[7]]))
            .collect())
    }
}
