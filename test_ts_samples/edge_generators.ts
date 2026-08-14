// Generator patterns for TypeScript
function* generatorDecl(): Generator<number> {
    yield 1;
    yield 2;
}

const generatorExpr = function*(): Generator<string> {
    yield "hello";
};

async function* asyncGen(): AsyncGenerator<number> {
    yield 1;
}

export function* exportedGen(): Generator<void> {
    yield;
}

export default function* defaultGen(): Generator<number> {
    yield 42;
}

// Positive control — regular function (should still be captured)
function normalFunc(): void {
    return;
}

// Positive control — arrow function (should still be captured)
const normalArrow = (): void => {
    return;
};

// Negative control — non-generator function expression (should NOT be captured)
const notAGen = function(): void {
    return;
};
