// Edge: code-like text inside strings and comments must be ignored.

// function fakeFunction() { return 1; }
// console.log("not a real call");

function realFunction() {
  const doc = `
    function documentedExample() {
      return "shown in docs, not indexed";
    }
  `;
  const sample = "use sort([3, 1]) and filter(x => x > 0)";
  return doc + sample;
}

function templateWithCalls(name) {
  const message = `hello ${name}, call print("x") now`;
  return message.toUpperCase();
}

function stringsOnly() {
  const a = "console.log('nested')";
  const b = 'alert("fake")';
  return a + b;
}

function commentMarkerInString() {
  // The string holds ``//`` but the call after it on the same line is real.
  const url = "https://example.com/a/b"; const n = post(url);
  return n;
}

function blockMarkerInString() {
  const s = "/* not a comment */ // nor this"; const t = post(s);
  return t;
}

function templateWithUrl(name) {
  const u = `https://example.com/${name}`; const r = fetchUrl(u);
  return r;
}