// Generics: constraints, defaults, conditional types, keyof.

interface HasId {
  id: string;
}

function findById<T extends HasId>(items: T[], id: string): T | undefined {
  return items.find((item) => item.id === id);
}

function mapValues<K extends string, V>(source: Record<K, V>, fn: (v: V) => V): Record<K, V> {
  const out = {} as Record<K, V>;
  for (const key of Object.keys(source) as K[]) {
    out[key] = fn(source[key]);
  }
  return out;
}

class Box<T = unknown> {
  constructor(private value: T) {}

  get(): T {
    return this.value;
  }

  set(next: T): void {
    this.value = next;
  }
}

type Unwrap<T> = T extends Promise<infer U> ? U : T;

function unwrap<T>(value: T): Unwrap<T> {
  return value as Unwrap<T>;
}

function keysOf<T extends object>(obj: T): (keyof T)[] {
  return Object.keys(obj) as (keyof T)[];
}