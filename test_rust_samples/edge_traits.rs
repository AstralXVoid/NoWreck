// Trait patterns — all trait and impl blocks should be captured.

trait Summary {
    fn summarize(&self) -> String;

    // Default method — still part of the trait
    fn preview(&self) -> String {
        let s = self.summarize();
        if s.len() > 20 {
            format!("{}...", &s[..20])
        } else {
            s
        }
    }
}

trait Serializable {
    fn to_json(&self) -> String;
    fn from_json(data: &str) -> Self where Self: Sized;
}

struct Article {
    title: String,
    content: String,
}

impl Summary for Article {
    fn summarize(&self) -> String {
        format!("{}: {}", self.title, &self.content[..50])
    }
}

impl Serializable for Article {
    fn to_json(&self) -> String {
        format!("{{\"title\":\"{}\"}}", self.title)
    }

    fn from_json(data: &str) -> Self {
        Article {
            title: data.to_string(),
            content: String::new(),
        }
    }
}

// Multiple traits on one struct
trait Display {
    fn fmt(&self) -> String;
}

trait Debug {
    fn debug(&self) -> String;
}

struct Point {
    x: f64,
    y: f64,
}

impl Display for Point {
    fn fmt(&self) -> String {
        format!("({}, {})", self.x, self.y)
    }
}

impl Debug for Point {
    fn debug(&self) -> String {
        format!("Point {{ x: {}, y: {} }}", self.x, self.y)
    }
}
