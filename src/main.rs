//! Rust coordinator for Kora's shared, tested backend.
//! This is not a standalone Rust download engine. Python remains required.
use std::env;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode};

fn python(root: &Path) -> Result<PathBuf, String> {
    if let Some(value) = env::var_os("KORA_PYTHON").filter(|value| !value.is_empty()) {
        let path = PathBuf::from(value);
        if path.is_file() { return Ok(path); }
        return Err("KORA_PYTHON points to a missing executable".into());
    }
    let bundled = root.join("runtime").join("python.exe");
    if bundled.is_file() { return Ok(bundled); }
    if let Ok(value) = std::fs::read_to_string(root.join("python-path.txt")) {
        let configured = PathBuf::from(value.trim());
        if configured.is_file() { return Ok(configured); }
    }
    if let Some(path) = env::var_os("PATH") {
        for directory in env::split_paths(&path) {
            let candidate = directory.join(if cfg!(windows) { "python.exe" } else { "python3" });
            if candidate.is_file() && !candidate.to_string_lossy().contains("WindowsApps") { return Ok(candidate); }
        }
    }
    Err("Python 3.10+ was not found; set KORA_PYTHON".into())
}

fn run() -> Result<i32, String> {
    let args: Vec<_> = env::args_os().skip(1).collect();
    if args.first().map(|s| s == "--version").unwrap_or(false) {
        println!("Kora {} (Rust coordinator; Python backend)", env!("CARGO_PKG_VERSION"));
        return Ok(0);
    }
    let exe = env::current_exe().map_err(|e| e.to_string())?;
    let root = application_root(&exe)?;
    let interpreter = python(&root)?;
    if args.first().map(|s| s == "rea").unwrap_or(false) {
        // Discovery is shared with the desktop edition; REA itself is launched
        // directly by Rust with an argument vector, never by a command shell.
        let discovery = Command::new(&interpreter)
            .env("PYTHONUTF8", "1")
            .arg(root.join("kora.py")).arg("rea-paths")
            .output().map_err(|e| e.to_string())?;
        if !discovery.status.success() { return Err(String::from_utf8_lossy(&discovery.stderr).into_owned()); }
        let text = String::from_utf8(discovery.stdout).map_err(|e| e.to_string())?;
        let (node, entry) = parse_discovery(&text)?;
        let status = Command::new(node).arg(entry).args(&args[1..])
            .status().map_err(|e| e.to_string())?;
        return Ok(status.code().unwrap_or(1));
    }
    let status = Command::new(interpreter).env("PYTHONUTF8", "1").arg(root.join("kora.py"))
        .args(args).status().map_err(|e| e.to_string())?;
    Ok(status.code().unwrap_or(1))
}

fn parse_discovery(text: &str) -> Result<(&str, &str), String> {
    let lines: Vec<_> = text.lines().collect();
    if lines.len() != 2 || lines.iter().any(|line| line.is_empty() || line.contains('\0')) {
        return Err("Invalid REA discovery response".into());
    }
    Ok((lines[0], lines[1]))
}

fn application_root(exe: &Path) -> Result<PathBuf, String> {
    // Support both the packaged executable and cargo run's target/debug or
    // target/release location. Prefer code adjacent to the executable.
    for directory in exe.ancestors().skip(1).take(4) {
        if directory.join("kora.py").is_file() {
            return Ok(directory.to_path_buf());
        }
    }
    Err("Kora's Python backend is missing. Keep kora.exe beside kora.py, or run from the complete source package.".into())
}

fn main() -> ExitCode {
    match run() {
        Ok(code) => ExitCode::from(code.clamp(0, 255) as u8),
        Err(error) => { eprintln!("Kora: {error}"); ExitCode::FAILURE }
    }
}

#[cfg(test)]
mod tests {
    use super::parse_discovery;

    #[test]
    fn discovery_preserves_spaces_unicode_and_crlf() {
        let (node, entry) = parse_discovery("C:\\Program Files\\node.exe\r\nC:\\Kora café\\rea.mjs\r\n").unwrap();
        assert_eq!(node, "C:\\Program Files\\node.exe");
        assert_eq!(entry, "C:\\Kora café\\rea.mjs");
    }

    #[test]
    fn discovery_rejects_extra_lines_and_nul_bytes() {
        assert!(parse_discovery("node\nentry\nextra").is_err());
        assert!(parse_discovery("node\nent\0ry").is_err());
        assert!(parse_discovery("node\n").is_err());
    }
}
