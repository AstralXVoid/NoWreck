// Realistic module: a typed event emitter.

type Handler<T> = (payload: T) => void;
type Unsubscribe = () => void;

interface Subscription<T> {
  event: string;
  handler: Handler<T>;
}

const DEFAULT_CAPACITY = 100;

class TypedEmitter {
  private handlers = new Map<string, Handler<unknown>[]>();

  constructor(private capacity: number = DEFAULT_CAPACITY) {}

  on<T>(event: string, handler: Handler<T>): Unsubscribe {
    const list = this.handlers.get(event) ?? [];
    list.push(handler as Handler<unknown>);
    this.handlers.set(event, list);
    return () => this.off(event, handler as Handler<unknown>);
  }

  off<T>(event: string, handler: Handler<T>): void {
    const list = this.handlers.get(event);
    if (!list) {
      return;
    }
    const index = list.indexOf(handler as Handler<unknown>);
    if (index >= 0) {
      list.splice(index, 1);
    }
  }

  emit<T>(event: string, payload: T): void {
    const list = this.handlers.get(event) ?? [];
    for (const handler of list) {
      handler(payload);
    }
  }

  count(event: string): number {
    return (this.handlers.get(event) ?? []).length;
  }
}

function createEmitter<T>(capacity?: number): TypedEmitter {
  return new TypedEmitter(capacity);
}

export { TypedEmitter, createEmitter };