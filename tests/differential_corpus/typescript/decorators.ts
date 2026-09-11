// Decorators: method decorators must fold into the method hash
// (v16 Accepted Edges #1 — TS attaches decorators as siblings).

function log(target: unknown, key: string): void {
  console.log(`calling ${key}`);
}

function sealed(constructor: Function): void {
  Object.seal(constructor);
}

function readonly(target: unknown, key: string, descriptor: PropertyDescriptor): PropertyDescriptor {
  descriptor.writable = false;
  return descriptor;
}

@sealed
class Service {
  private calls = 0;

  @log
  @readonly
  handle(request: string): string {
    this.calls += 1;
    return `handled:${request}`;
  }

  @log
  async process(items: number[]): Promise<number> {
    return items.reduce((acc, item) => acc + item, 0);
  }
}

function useService(): string {
  const service = new Service();
  return service.handle("x");
}