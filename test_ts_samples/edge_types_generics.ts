// Generic type-level declarations
interface Box<T> {
    value: T;
}

type Pair<A, B> = [A, B];

enum Level {
    Low,
    High,
}

class Holder<T> {
    item: T | null = null;
}
