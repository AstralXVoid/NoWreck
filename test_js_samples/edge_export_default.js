// Edge case 10: export default with named and anonymous values

// --- Anonymous default exports (correctly NOT captured — no name) ---

export default function() {}  // anonymous default

const namedDefault = 42;
export default namedDefault;  // re-export of const (no declaration field)

export default class {}  // anonymous class default

// Anonymous arrow default — no name to capture
export default () => {
    return "default arrow";
};

// --- Named default exports (DO have `declaration` field — captured) ---

export default function explicitDefault() {
    return "explicit";
}

export default class Bar {
    barMethod() {
        return "bar";
    }
}

// --- Regular named exports alongside (also captured) ---

export function namedFn() {}
export class NamedClass {
    doThing() {}
}
