// v4: Generator function patterns — now captured (was deferred in v3)

// 1. Basic generator declaration
function* idGenerator() {
    let id = 0;
    while (true) {
        yield id++;
    }
}

// 2. Async generator declaration
async function* streamGenerator(query) {
    for await (const item of query) {
        yield item;
    }
}

// 3. Generator expression assigned to const
const counter = function*() {
    let count = 0;
    while (true) {
        yield count++;
    }
};

// 4. Generator expression assigned to let
let range = function*(start, end) {
    for (let i = start; i < end; i++) {
        yield i;
    }
};

// 5. Generator expression assigned via var
var sequence = function*() {
    yield 1;
    yield 2;
    yield 3;
};

// 6. Exported generator declaration
export function* exportedGenerator() {
    yield 'exported';
}

// 7. Default-exported generator declaration
export default function* exportedDefaultGen() {
    yield 'default exported';
}

// 8. Regular function declaration (positive control — must still work)
function normalFunction() {
    return 'normal';
}

// 9. Regular arrow function (positive control — must still work)
const normalArrow = () => 'normal';

// 10. Non-generator function expression (should NOT be captured — negative control)
const notAGenerator = function() {
    return 'not a generator';
};
