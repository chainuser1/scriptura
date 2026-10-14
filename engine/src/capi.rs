//! C ABI for Dart FFI. JSON in, JSON out; every returned string is owned by the engine and must be released with
//! `se_free_string`. Panics never cross the boundary.
//!
//! ```c
//! void*  se_open(const char* config_json, char** error_json);   // NULL on failure, *error_json set
//! char*  se_request(void* engine, const char* request_json);    // always a JSON object, never NULL
//! void   se_cancel(void* engine, uint64_t request_id);
//! void   se_close(void* engine);
//! void   se_free_string(char* s);
//! char*  se_extract_zip(const char* zip_path, const char* out_dir);  // {"files","bytes"} or {"error"}
//! const char* se_version(void);                                  // static, do not free
//! ```

use crate::engine::{Config, Engine};
use std::ffi::{c_char, c_void, CStr, CString};
use std::panic::{catch_unwind, AssertUnwindSafe};

fn to_c(s: String) -> *mut c_char {
    CString::new(s.replace('\0', " ")).unwrap().into_raw()
}

fn error_json(code: &str, message: &str) -> String {
    serde_json::json!({"error": {"code": code, "message": message}}).to_string()
}

unsafe fn text<'a>(p: *const c_char) -> Result<&'a str, String> {
    if p.is_null() {
        return Err("null string".into());
    }
    CStr::from_ptr(p).to_str().map_err(|e| e.to_string())
}

/// # Safety
/// `config_json` must be a valid NUL-terminated UTF-8 string; `error_json` null or a valid out-pointer.
#[no_mangle]
pub unsafe extern "C" fn se_open(config_json: *const c_char, error_json_out: *mut *mut c_char) -> *mut c_void {
    let r = catch_unwind(AssertUnwindSafe(|| -> Result<Engine, String> {
        let cfg: Config = serde_json::from_str(text(config_json)?).map_err(|e| format!("config: {e}"))?;
        Engine::open(cfg)
    }));
    let err = match r {
        Ok(Ok(e)) => return Box::into_raw(Box::new(e)) as *mut c_void,
        Ok(Err(m)) => m,
        Err(_) => "engine panicked while opening".to_string(),
    };
    if !error_json_out.is_null() {
        *error_json_out = to_c(error_json("open_failed", &err));
    }
    std::ptr::null_mut()
}

/// # Safety
/// `engine` from `se_open` and not yet closed; `request_json` a valid NUL-terminated UTF-8 string.
#[no_mangle]
pub unsafe extern "C" fn se_request(engine: *mut c_void, request_json: *const c_char) -> *mut c_char {
    if engine.is_null() {
        return to_c(error_json("invalid_input", "engine is null"));
    }
    let e = &*(engine as *const Engine);
    let out = catch_unwind(AssertUnwindSafe(|| match text(request_json).and_then(|s| serde_json::from_str(s).map_err(|e| e.to_string())) {
        Ok(v) => e.handle(&v).to_string(),
        Err(m) => error_json("invalid_input", &m),
    }));
    to_c(out.unwrap_or_else(|_| error_json("internal", "engine panicked")))
}

/// # Safety
/// `engine` from `se_open` and not yet closed.
#[no_mangle]
pub unsafe extern "C" fn se_cancel(engine: *mut c_void, request_id: u64) {
    if !engine.is_null() {
        (*(engine as *const Engine)).cancel(request_id);
    }
}

/// # Safety
/// `engine` from `se_open`; it must not be used afterwards.
#[no_mangle]
pub unsafe extern "C" fn se_close(engine: *mut c_void) {
    if !engine.is_null() {
        drop(Box::from_raw(engine as *mut Engine));
    }
}

/// # Safety
/// `s` returned by this library and not yet freed, or null.
#[no_mangle]
pub unsafe extern "C" fn se_free_string(s: *mut c_char) {
    if !s.is_null() {
        drop(CString::from_raw(s));
    }
}

/// Extracts a pack archive into `out_dir` (top-level folder stripped). Returns `{"files":n,"bytes":n}` or an error object.
///
/// # Safety
/// Both arguments must be valid NUL-terminated UTF-8 strings.
#[no_mangle]
pub unsafe extern "C" fn se_extract_zip(zip_path: *const c_char, out_dir: *const c_char) -> *mut c_char {
    let r = catch_unwind(AssertUnwindSafe(|| -> Result<(u64, u64), String> {
        crate::unpack::extract(std::path::Path::new(text(zip_path)?), std::path::Path::new(text(out_dir)?))
    }));
    to_c(match r {
        Ok(Ok((files, bytes))) => serde_json::json!({"files": files, "bytes": bytes}).to_string(),
        Ok(Err(m)) => error_json("extract_failed", &m),
        Err(_) => error_json("internal", "extraction panicked"),
    })
}

#[no_mangle]
pub extern "C" fn se_version() -> *const c_char {
    concat!(env!("CARGO_PKG_VERSION"), "\0").as_ptr() as *const c_char
}
