// Generic type-level declarations (TSX)
interface ListItem<T> {
    value: T;
}

type Result<T> = { ok: true; data: T } | { ok: false };
