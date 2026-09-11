// Classes: methods, getters/setters, static members, class fields.

class Counter {
  static defaultStep = 1;

  constructor(initial = 0) {
    this._value = initial;
  }

  increment(step = Counter.defaultStep) {
    this._value += step;
    return this._value;
  }

  get value() {
    return this._value;
  }

  set value(next) {
    if (next < 0) {
      throw new Error("negative not allowed");
    }
    this._value = next;
  }

  static from(seed) {
    return new Counter(seed);
  }

  describe() {
    return `counter=${this._value}`;
  }

  incrementBy = (step) => this.increment(step);
}

const shared = Counter.from(10);