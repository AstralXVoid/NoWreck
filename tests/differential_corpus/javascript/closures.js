// Closures: nested functions, IIFE (not a symbol), returned closures.

function makeAdder(base) {
  return function addTo(value) {
    return base + value;
  };
}

function makeCounter() {
  let count = 0;
  return {
    next() {
      count += 1;
      return count;
    },
    reset() {
      count = 0;
    },
  };
}

const addFive = makeAdder(5);
const counter = makeCounter();

// IIFE assigned to a variable: not a symbol.
const boot = (function () {
  const secret = "s3cret";
  return function getSecret() {
    return secret;
  };
})();

function outer() {
  function inner() {
    return 1;
  }
  function deeper() {
    function innermost() {
      return inner() + 1;
    }
    return innermost();
  }
  return deeper();
}