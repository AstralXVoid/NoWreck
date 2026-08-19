// Derive macros and attribute patterns.
// Attributes and derive macros are structural decoration — NoWreck
// captures the underlying declaration regardless.

#[derive(Debug, Clone, Serialize, Deserialize)]
struct Config {
    name: String,
    value: i32,
}

#[derive(PartialEq, Eq, Hash)]
struct Point {
    x: f64,
    y: f64,
}

#[derive(Default)]
struct Buffer {
    data: Vec<u8>,
}

// Multiple attributes on one item
#[cfg(target_os = "linux")]
#[derive(Debug)]
fn platform_specific() -> bool {
    true
}

// Attribute on a trait
#[async_trait]
trait Repository {
    fn find(&self, id: u64) -> Option<String>;
}

// Attribute on an enum
#[derive(Clone, Copy)]
enum Direction {
    North,
    South,
    East,
    West,
}

// Attribute on a type alias
#[allow(dead_code)]
type Unused = i64;

// Derive with complex paths
#[derive(serde::Serialize, serde::Deserialize)]
struct SerdeItem {
    id: u32,
}
