// Basic module: plain functions, pub functions, generics on functions.

const PREFIX: &str = "app";

fn greet(name: &str, excited: bool) -> String {
    let message = format!("{PREFIX}: {name}");
    if excited {
        return message.to_uppercase();
    }
    message
}

pub fn sum(values: &[i64]) -> i64 {
    values.iter().sum()
}

fn internal_helper(value: i64) -> i64 {
    value * 2
}

pub(crate) fn compute_total(values: &[i64]) -> i64 {
    values.iter().map(|v| internal_helper(*v)).sum()
}

fn first_or<T>(items: &[T], fallback: T) -> T
where
    T: Clone,
{
    items.first().cloned().unwrap_or(fallback)
}

fn main() {
    let total = compute_total(&[1, 2, 3]);
    println!("{total}");
}