// Formatting variety: layout must never change symbol identity.

function multilineCall(
  first: number,
  second: number, // trailing comment
): number {
  return first + second;
}

class Wide {
  method(
    a: number,
    b: number,
  ): number {
    return a - b;
  }
}

const    spaced   : (x: number) => number = (x) => x;

function compact(){return 1;}

const oneLiner = (): string => "short";

const result: number = multilineCall(
  1,
  2,
);

type   weird  =   string  |   number;

interface Loose {
  a?: string;
  b?: number;
}