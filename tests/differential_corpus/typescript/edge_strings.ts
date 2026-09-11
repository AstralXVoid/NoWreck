// Edge: code-like text inside strings and comments must be ignored.

// interface fakeInterface {}
// function fakeFunction(): number { return 1; }

function realFunction(): string {
  const doc = `
    interface documentedInterface {
      method(): void;
    }
  `;
  const sample = "use sort([3, 1]) and filter(x => x > 0)";
  return doc + sample;
}

function templateWithCalls(name: string): string {
  const message = `hello ${name}, call print("x") now`;
  return message.toUpperCase();
}

const literal = "enum FakeEnum { A }";

function commentMarkerInString(): string {
  // The string holds ``//`` but the call after it on the same line is real.
  const url = "https://example.com/a/b"; const n = post(url);
  return n;
}

function templateWithUrl(name: string): string {
  const u = `https://example.com/${name}`; const r = fetchUrl(u);
  return r;
}