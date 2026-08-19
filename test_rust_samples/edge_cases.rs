// Edge cases: nested functions, macros, generics, lifetimes

pub fn public_function() -> i32 {
    42
}

fn outer() {
    fn inner() {
        // nested — should NOT be captured separately
    }
    inner();
}

// Function with generics
fn first<T>(items: &[T]) -> Option<&T> {
    items.first()
}

// Struct with generics
struct Point<T> {
    x: T,
    y: T,
}

impl<T> Point<T> {
    fn new(x: T, y: T) -> Self {
        Point { x, y }
    }
}

// Trait with default method
trait Summary {
    fn summarize(&self) -> String;

    fn preview(&self) -> String {
        format!("({}...)", &self.summarize()[..10])
    }
}

// Enum with data
enum Message {
    Quit,
    Move { x: i32, y: i32 },
    Write(String),
}

// Type alias with generics
type Matrix<T> = Vec<Vec<T>>;
