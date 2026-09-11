// Generics: generic structs/fns/impls, bounds, associated types.

trait HasId {
    type Id;

    fn id(&self) -> Self::Id;
}

struct Entity<T> {
    value: T,
}

struct Registry<K, V> {
    entries: Vec<(K, V)>,
}

impl<T> Entity<T> {
    fn new(value: T) -> Entity<T> {
        Entity { value }
    }

    fn get(&self) -> &T {
        &self.value
    }
}

impl<K, V> Registry<K, V>
where
    K: Eq + std::hash::Hash + Clone,
    V: Clone,
{
    fn new() -> Registry<K, V> {
        Registry { entries: Vec::new() }
    }

    fn insert(&mut self, key: K, value: V) {
        self.entries.push((key, value));
    }

    fn find(&self, key: &K) -> Option<&V> {
        self.entries
            .iter()
            .find(|(k, _)| k == key)
            .map(|(_, v)| v)
    }
}

fn largest<T: PartialOrd + Clone>(items: &[T]) -> Option<T> {
    items.iter().max_by(|a, b| a.partial_cmp(b).unwrap()).cloned()
}

struct User {
    uid: u64,
}

impl HasId for User {
    type Id = u64;

    fn id(&self) -> u64 {
        self.uid
    }
}

fn get_id<T: HasId>(value: &T) -> T::Id {
    value.id()
}