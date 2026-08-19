// Core Rust constructs — all should be captured as symbols.

fn greet(name: &str) -> String {
    format!("Hello, {}!", name)
}

fn add(a: i32, b: i32) -> i32 {
    a + b
}

struct User {
    name: String,
    age: u32,
}

impl User {
    fn new(name: &str, age: u32) -> Self {
        User {
            name: name.to_string(),
            age,
        }
    }

    fn display(&self) -> String {
        format!("{} ({})", self.name, self.age)
    }

    fn update_age(&mut self, age: u32) {
        self.age = age;
    }
}

trait Drawable {
    fn draw(&self);
}

enum Color {
    Red,
    Green,
    Blue,
}

type UserId = u64;

const MAX_AGE: u32 = 150;
