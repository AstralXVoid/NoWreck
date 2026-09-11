// Error handling: Result, custom error enums, ?, unwrap/or_else.

use std::fmt;

#[derive(Debug)]
pub enum ConfigError {
    Empty,
    BadLine(String),
    Io(std::io::Error),
}

impl fmt::Display for ConfigError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ConfigError::Empty => write!(f, "empty config"),
            ConfigError::BadLine(line) => write!(f, "bad line: {line}"),
            ConfigError::Io(err) => write!(f, "io: {err}"),
        }
    }
}

impl std::error::Error for ConfigError {}

fn parse_config(raw: &str) -> Result<std::collections::HashMap<String, String>, ConfigError> {
    if raw.trim().is_empty() {
        return Err(ConfigError::Empty);
    }
    let mut result = std::collections::HashMap::new();
    for line in raw.lines() {
        let Some((key, value)) = line.split_once('=') else {
            return Err(ConfigError::BadLine(line.to_string()));
        };
        result.insert(key.trim().to_string(), value.trim().to_string());
    }
    Ok(result)
}

fn load_config(path: &str) -> Result<std::collections::HashMap<String, String>, ConfigError> {
    let raw = std::fs::read_to_string(path).map_err(ConfigError::Io)?;
    parse_config(&raw)
}

fn mode_or_default(config: &std::collections::HashMap<String, String>) -> String {
    config.get("mode").cloned().unwrap_or_else(|| "dev".to_string())
}