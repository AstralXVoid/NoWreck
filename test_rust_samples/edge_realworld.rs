// Real-world Rust patterns — async, Result, Option, pub use, macros.

use std::collections::HashMap;
pub use std::io::Error;

// Async function
async fn fetch_data(url: &str) -> Result<String, Box<dyn std::error::Error>> {
    Ok(format!("data from {}", url))
}

// Function returning Result
fn parse_config(path: &str) -> Result<Config, String> {
    Ok(Config {
        name: path.to_string(),
        value: 0,
    })
}

// Function with Option
fn find_user(id: u64) -> Option<User> {
    None
}

// Function with match
fn classify(score: i32) -> &'static str {
    match score {
        0..=50 => "low",
        51..=90 => "medium",
        _ => "high",
    }
}

// Struct with impl
struct Config {
    name: String,
    value: i32,
}

impl Config {
    fn new(name: &str) -> Self {
        Config { name: name.to_string(), value: 0 }
    }
}

// Struct with derive
#[derive(Debug, Clone)]
struct User {
    name: String,
    age: u32,
}

impl User {
    fn greet(&self) -> String {
        format!("Hi, I'm {}", self.name)
    }
}

// Trait with default impl
trait Describable {
    fn describe(&self) -> String;

    fn short_description(&self) -> String {
        "no description".to_string()
    }
}

// Enum with variants
#[derive(Debug)]
enum Status {
    Active,
    Inactive,
    Banned { reason: String },
}

impl Status {
    fn is_active(&self) -> bool {
        matches!(self, Status::Active)
    }
}

// Type alias
type Result<T> = std::result::Result<T, String>;

// Function using macro invocations (calls, not declarations)
fn log_and_return(msg: &str) -> &str {
    println!("{}", msg);   // macro invocation — NOT a function symbol
    dbg!(msg);             // macro invocation — NOT a function symbol
    msg
}

// Pub use re-export
pub use self::Config as AppConfig;

// Static and const (not captured as symbols — only items with names)
const MAX_RETRIES: u32 = 3;
static COUNTER: u32 = 0;
