// Edge case 10: export default with named and anonymous values

// These should NOT be captured (no declaration field, they use 'value' field)
export default function() {}  // anonymous default

const namedDefault = 42;
export default namedDefault;  // re-export of const, no declaration field

// export default class — should NOT crash, even if not captured
export default class {}  // anonymous class default

// Edge: export default named function — uses 'value' field, not 'declaration'
export default function explicitDefault() {
    return "explicit";
}

// export default arrow — also uses 'value' field
export default () => {
    return "default arrow";
};

// Regular named export alongside — these SHOULD be captured
export function namedFn() {}
export class NamedClass {
    doThing() {}
}
