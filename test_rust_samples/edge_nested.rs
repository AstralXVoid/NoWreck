// Nested and module patterns — only top-level items captured.

fn outer() {
    fn inner() {
        // nested function — NOT captured
    }
    inner();
    helper();
}

fn helper() -> i32 {
    42
}

mod utilities {
    pub fn util_function() -> bool {
        true
    }

    pub struct Config {
        pub value: i32,
    }

    impl Config {
        pub fn default() -> Self {
            Config { value: 0 }
        }
    }
}

use std::collections::HashMap;

fn process_map(data: HashMap<String, i32>) -> i32 {
    data.values().sum()
}

// Multiple nested levels
fn level_one() {
    fn level_two() {
        fn level_three() {
            // deeply nested — NOT captured
        }
        level_three();
    }
    level_two();
}
