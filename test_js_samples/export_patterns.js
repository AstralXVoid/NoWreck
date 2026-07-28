// Test case 4: Export patterns — the gap we deliberately fix before Phase 2

// Named export: function declaration
export function formatDate(date) {
    return date.toISOString();
}

// Named export: class declaration
export class Logger {
    constructor(prefix) {
        this.prefix = prefix;
    }

    log(message) {
        console.log(`[${this.prefix}] ${message}`);
    }

    warn(message) {
        console.warn(`[${this.prefix}] ${message}`);
    }
}

// Named export: arrow function assigned to const
export const parseJson = (text) => {
    return JSON.parse(text);
};

// Named export: arrow function (implicit return)
export const identity = (x) => x;

// Named export via var (edge case, rare but valid)
export var legacyMode = () => {
    return false;
};

// Negative case: export default anonymous function — no symbol name, should NOT be captured
export default function() {
    return "default";
}

// Negative case: bare export { ... } — re-exports, should NOT create symbols in this file
export { formatDate };
