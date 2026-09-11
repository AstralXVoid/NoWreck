// Edge: export forms, anonymous exports (no symbol), re-exports.

export function namedExport() {
  return 1;
}

export class ExportedClass {
  method() {
    return 2;
  }
}

export const arrowExport = (x) => x + 1;

export const generatorExport = function* () {
  yield 3;
};

export default function anonymousDefault() {
  return 4;
}

export default class {
  anon() {
    return 5;
  }
}

export { namedExport as renamedExport };