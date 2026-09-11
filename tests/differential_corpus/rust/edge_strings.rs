// Edge: code-like text inside strings and comments must be ignored.
// fn fake_function() -> i64 { 1 }
// Example: println!("not a real call");

fn real_function() -> String {
    let doc = r#"
        fn documented_example() -> i64 {
            "shown in docs, not indexed"
        }
    "#;
    let sample = "use sum([3, 1]) and filter(|x| x > 0)";
    format!("{doc}{sample}")
}

fn raw_contains_code() -> String {
    r##"fn also_fake() { println!("nested"); }"##.to_string()
}

fn byte_and_char() -> (Vec<u8>, char) {
    let bytes = b"print('nested')";
    let ch = 'x';
    (bytes.to_vec(), ch)
}

// Lifetimes must survive stripping (they look like char literals).
fn longest<'a>(a: &'a str, b: &'a str) -> &'a str {
    if a.len() > b.len() { a } else { b }
}

// A ``//`` inside a string must not start a comment that eats the call
// after it on the same line.
fn comment_marker_in_string() -> String {
    let url = "https://example.com/a/b"; let n = post(url);
    n
}

fn raw_with_url() -> String {
    let url = r#"https://example.com/a/b"#; let n = post(url);
    n
}