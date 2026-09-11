// Object literals with methods: methods are NOT symbols (documented
// boundary — only class methods and named/arrow functions are).

const formatter = {
  prefix: "[fmt]",

  format(value) {
    return `${this.prefix} ${value}`;
  },

  join(values, sep = ",") {
    return values.join(sep);
  },

  async asyncFormat(value) {
    return this.format(value);
  },
};

const handler = {
  handle(event) {
    return event.type;
  },
  *iterate(items) {
    for (const item of items) {
      yield item;
    }
  },
};

function useFormatters() {
  return formatter.format(handler.handle({ type: "click" }));
}