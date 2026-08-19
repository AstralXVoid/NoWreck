// Generic patterns — all should be captured.

fn first<T>(items: &[T]) -> Option<&T> {
    items.first()
}

fn swap<T>(a: T, b: T) -> (T, T) {
    (b, a)
}

struct Pair<T> {
    first: T,
    second: T,
}

impl<T> Pair<T> {
    fn new(first: T, second: T) -> Self {
        Pair { first, second }
    }

    fn first(&self) -> &T {
        &self.first
    }
}

struct KeyValue<K, V> {
    key: K,
    value: V,
}

impl<K, V> KeyValue<K, V> {
    fn new(key: K, value: V) -> Self {
        KeyValue { key, value }
    }
}

// Where clause
fn longest<'a>(x: &'a str, y: &'a str) -> &'a str {
    if x.len() > y.len() { x } else { y }
}

// Generic trait bound
fn print_all<T: std::fmt::Display>(items: &[T]) {
    for item in items {
        println!("{}", item);
    }
}

// Multiple generic parameters
fn zip_with<A, B, F>(a: &[A], b: &[B], f: F) -> Vec<(A, B)>
where
    F: Fn(&A, &B) -> (A, B),
    A: Clone,
    B: Clone,
{
    a.iter().zip(b.iter()).map(|(x, y)| f(x, y)).collect()
}
