// Negative tests — items that should NOT be captured as symbols.
// NoWreck captures only top-level declarations: functions, structs,
// traits, enums, type aliases, and impl methods.
// Members (fields, variants, trait method signatures) are NOT captured.

trait Repository {
    // These method signatures are NOT captured:
    fn find(&self, id: u64) -> Option<String>;
    fn save(&self, data: &str) -> bool;
    fn delete(&self, id: u64);
}

struct Article {
    // These fields are NOT captured:
    title: String,
    content: String,
    views: u64,
}

enum Color {
    // These variants are NOT captured:
    Red,
    Green,
    Blue,
    Named { r: u8, g: u8, b: u8 },
}

// Nested functions inside a function body — NOT captured
fn outer() {
    fn helper() -> i32 {
        42
    }
    let _ = helper();
}

// Items inside an impl block ARE captured (as methods),
// but the impl block itself is NOT a symbol.
impl Article {
    fn summary(&self) -> String {
        format!("{}: {}", self.title, &self.content[..50])
    }
}

// Items inside mod blocks are NOT captured (only top-level)
mod internal {
    pub fn secret() -> i32 { 42 }
    pub struct Hidden { pub value: i32 }
}
