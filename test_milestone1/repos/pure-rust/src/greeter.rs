pub fn greet(name: &str) -> String {
    let greeting = format_greeting(name);
    greeting
}

fn format_greeting(name: &str) -> String {
    format!("Hello, {}!", name)
}

pub fn farewell(name: &str) -> String {
    format!("Goodbye, {}!", name)
}
