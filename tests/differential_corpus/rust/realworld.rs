// Realistic module: a small LRU cache with tests-style helpers.

use std::collections::HashMap;
use std::collections::VecDeque;

pub struct Cache {
    capacity: usize,
    store: HashMap<String, Entry>,
    order: VecDeque<String>,
}

struct Entry {
    key: String,
    value: String,
    tags: Vec<String>,
}

impl Cache {
    pub fn new(capacity: usize) -> Cache {
        Cache {
            capacity,
            store: HashMap::new(),
            order: VecDeque::new(),
        }
    }

    pub fn get(&mut self, key: &str) -> Option<&str> {
        if !self.store.contains_key(key) {
            return None;
        }
        self.touch(key);
        self.store.get(key).map(|entry| entry.value.as_str())
    }

    pub fn set(&mut self, key: &str, value: String, tags: Vec<String>) {
        if self.store.len() >= self.capacity && !self.store.contains_key(key) {
            self.evict();
        }
        let entry = Entry {
            key: key.to_string(),
            value,
            tags,
        };
        self.store.insert(key.to_string(), entry);
        self.order.push_back(key.to_string());
    }

    pub fn len(&self) -> usize {
        self.store.len()
    }

    pub fn is_empty(&self) -> bool {
        self.store.is_empty()
    }

    fn touch(&mut self, key: &str) {
        self.order.retain(|k| k != key);
        self.order.push_back(key.to_string());
    }

    fn evict(&mut self) {
        if let Some(oldest) = self.order.pop_front() {
            self.store.remove(&oldest);
        }
    }
}

pub fn slugify(text: &str) -> String {
    text.to_lowercase()
        .chars()
        .map(|c| if c.is_alphanumeric() { c } else { '-' })
        .collect::<String>()
        .trim_matches('-')
        .to_string()
}

pub fn process(records: Vec<(String, String)>, cache: &mut Cache) -> Vec<String> {
    let mut out = Vec::new();
    for (name, value) in records {
        let key = slugify(&name);
        match cache.get(&key) {
            Some(cached) => out.push(format!("cached:{cached}")),
            None => {
                cache.set(&key, value, Vec::new());
                out.push(format!("fresh:{key}"));
            }
        }
    }
    out
}