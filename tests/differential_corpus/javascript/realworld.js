// Realistic module: a small event bus with subscriptions.

const DEFAULT_CAPACITY = 100;

class EventBus {
  constructor(capacity = DEFAULT_CAPACITY) {
    this.capacity = capacity;
    this.subscribers = new Map();
    this.queue = [];
  }

  subscribe(event, handler) {
    if (!this.subscribers.has(event)) {
      this.subscribers.set(event, []);
    }
    this.subscribers.get(event).push(handler);
    return () => this.unsubscribe(event, handler);
  }

  unsubscribe(event, handler) {
    const handlers = this.subscribers.get(event);
    if (!handlers) {
      return;
    }
    const index = handlers.indexOf(handler);
    if (index >= 0) {
      handlers.splice(index, 1);
    }
  }

  publish(event, payload) {
    const handlers = this.subscribers.get(event) || [];
    for (const handler of handlers) {
      this.enqueue(() => handler(payload));
    }
  }

  enqueue(job) {
    if (this.queue.length >= this.capacity) {
      this.queue.shift();
    }
    this.queue.push(job);
  }

  drain() {
    while (this.queue.length > 0) {
      const job = this.queue.shift();
      job();
    }
  }

  size() {
    return this.subscribers.size;
  }
}

function createBus(capacity) {
  return new EventBus(capacity);
}

module.exports = { EventBus, createBus };