// Traits: trait declarations, impl Trait for X, default methods.

trait Drawable {
    fn draw(&self) -> String;

    fn describe(&self) -> String {
        format!("drawable: {}", self.draw())
    }
}

trait Area {
    fn area(&self) -> f64;
}

pub trait Named {
    fn name(&self) -> &str;
}

struct Circle {
    radius: f64,
}

struct Square {
    side: f64,
}

struct Person {
    full_name: String,
}

impl Drawable for Circle {
    fn draw(&self) -> String {
        format!("circle({})", self.radius)
    }
}

impl Area for Circle {
    fn area(&self) -> f64 {
        std::f64::consts::PI * self.radius * self.radius
    }
}

impl Drawable for Square {
    fn draw(&self) -> String {
        format!("square({})", self.side)
    }
}

impl Area for Square {
    fn area(&self) -> f64 {
        self.side * self.side
    }
}

impl Named for Person {
    fn name(&self) -> &str {
        &self.full_name
    }
}

fn total_area(shapes: &[&dyn Area]) -> f64 {
    shapes.iter().map(|s| s.area()).sum()
}