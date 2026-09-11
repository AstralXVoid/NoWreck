// Edge: call shapes.
// - obj.method(), a.b.c(), this.foo() captured.
// - f().bar() (receiver is a call) excluded.
// - dunder attrs excluded.
// - optional chaining a?.b() captured.

class Widget {
  constructor(name) {
    this.name = name;
  }

  label() {
    return this.name.toUpperCase();
  }

  describe() {
    return `${this.prefix()}:${this.label()}`;
  }

  prefix() {
    return "W";
  }
}

function formatWidget(widget) {
  return widget.describe();
}

function chain(registry) {
  registry.get("a").put("b");
  return outer.invoke(registry.fetch());
}

function optionalChain(store) {
  return store?.get("key")?.value;
}

function dunderCall(widget) {
  return widget.toString();
}

function receivers() {
  const xs = [1, 2, 3];
  return xs.map((x) => x * 2).filter((x) => x > 1);
}