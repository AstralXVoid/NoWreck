// Closure patterns — closures themselves are NOT captured (only top-level fns/structs/etc).
// But functions that accept or return closures ARE captured.

fn apply_to_vec<F>(items: Vec<i32>, f: F) -> Vec<i32>
where
    F: Fn(i32) -> i32,
{
    items.into_iter().map(f).collect()
}

fn make_adder(n: i32) -> impl Fn(i32) -> i32 {
    move |x| x + n
}

fn filter_positive(items: Vec<i32>) -> Vec<i32> {
    items.into_iter().filter(|x| *x > 0).collect()
}

fn process_data(data: &[i32]) -> i32 {
    let doubled: Vec<i32> = data.iter().map(|x| x * 2).collect();
    let sum: i32 = doubled.iter().sum();
    sum
}

// Closure stored in a variable — the closure itself is NOT a top-level symbol
// but process_items IS.
fn process_items<F>(items: &[i32], transform: F) -> Vec<i32>
where
    F: Fn(i32) -> i32,
{
    items.iter().map(|&x| transform(x)).collect()
}
