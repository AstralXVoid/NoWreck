// Edge: optional chaining, non-null assertion, nullish coalescing.

interface Config {
  db?: {
    connect(uri: string): Promise<void>;
    pool?: {
      size(): number;
    };
  };
}

async function connect(config: Config, uri: string): Promise<void> {
  await config.db?.connect(uri);
}

function poolSize(config: Config): number {
  return config.db?.pool?.size() ?? 0;
}

function chain(store: Map<string, { get: (k: string) => string | undefined }>): string {
  return store.get("a")?.get("b") ?? "missing";
}

function nonNull(registry: { fetch(): { id(): string } | null }): string {
  return registry.fetch()!.id();
}

class Chainable {
  next?: Chainable;

  walk(): string {
    return this.next?.walk() ?? "end";
  }
}