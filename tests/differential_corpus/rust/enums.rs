// Enums: plain and data-carrying variants, match, impl on enums.

enum Color {
    Red,
    Green,
    Blue,
}

enum StatusCode {
    Ok = 200,
    NotFound = 404,
}

enum Message {
    Quit,
    Move { x: i64, y: i64 },
    Write(String),
    ChangeColor(u8, u8, u8),
}

pub enum MaybeError {
    None,
    Some(String),
}

impl Message {
    fn summary(&self) -> String {
        match self {
            Message::Quit => "quit".to_string(),
            Message::Move { x, y } => format!("move {x},{y}"),
            Message::Write(text) => format!("write {text}"),
            Message::ChangeColor(r, g, b) => format!("rgb {r}{g}{b}"),
        }
    }
}

fn describe(color: Color) -> &'static str {
    match color {
        Color::Red => "red",
        Color::Green => "green",
        Color::Blue => "blue",
    }
}

fn unwrap_or_empty(maybe: &MaybeError) -> &str {
    match maybe {
        MaybeError::None => "",
        MaybeError::Some(value) => value,
    }
}