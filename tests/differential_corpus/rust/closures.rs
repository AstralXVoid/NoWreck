// Closures: closures are NOT symbols (documented boundary — only fn
// items and impl methods are).

fn make_adder(base: i64) -> impl Fn(i64) -> i64 {
    move |value| base + value
}

fn apply_twice<F>(f: F, value: i64) -> i64
where
    F: Fn(i64) -> i64,
{
    f(f(value))
}

fn process(values: &[i64]) -> Vec<i64> {
    values
        .iter()
        .map(|v| v * 2)
        .filter(|v| *v > 10)
        .collect()
}

fn sort_by_score(mut items: Vec<(String, i64)>) -> Vec<(String, i64)> {
    items.sort_by(|a, b| b.1.cmp(&a.1));
    items
}

fn counter() -> impl FnMut() -> i64 {
    let mut count = 0;
    move || {
        count += 1;
        count
    }
}

pub fn run() -> i64 {
    let add_five = make_adder(5);
    apply_twice(add_five, 10)
}