// Classes: typed methods, implements, accessors, static members.

interface Repository<T> {
  find(id: string): T | undefined;
  save(item: T): void;
}

class InMemoryStore<T> implements Repository<T> {
  private items = new Map<string, T>();

  find(id: string): T | undefined {
    return this.items.get(id);
  }

  save(item: T): void {
    this.items.set(String(item), item);
  }

  get size(): number {
    return this.items.size;
  }

  static empty<T>(): InMemoryStore<T> {
    return new InMemoryStore<T>();
  }
}

class User {
  constructor(public id: string, private _name: string) {}

  get name(): string {
    return this._name;
  }

  set name(next: string) {
    if (!next.trim()) {
      throw new Error("empty name");
    }
    this._name = next;
  }

  describe(): string {
    return `${this.id}:${this.name}`;
  }
}

const store = InMemoryStore.empty<string>();