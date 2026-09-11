// Formatting variety: layout must never change symbol identity.

function multilineCall(
  first,
  second, // trailing comment
) {
  return first + second;
}

class Wide {
  method(
    a,
    b,
  ) {
    return a - b;
  }
}

const    spaced    = (x) => x;

function compact(){return 1;}

const oneLiner = () => "short";

let   reassigned  = function notArrow() { return 9; };

const result = multilineCall(
  1,
  2,
);