// Real-world JS patterns that should parse cleanly

// HOC pattern (higher-order component style)
function withLogging(Component) {
    return function Enhanced(props) {
        console.log('rendering', Component.name);
        return Component(props);
    };
}

// Curried functions (function returning function - only outer is top-level)
function curriedAdd(a) {
    return function(b) {
        return function(c) {
            return a + b + c;
        };
    };
}

// Function with default parameters
function createUser(name, email = 'unknown@example.com', role = 'user') {
    return { name, email, role };
}

// Function with rest params
function sumAll(...numbers) {
    return numbers.reduce((total, n) => total + n, 0);
}

// Function with destructured params
function processConfig({ url, method = 'GET', headers = {} }) {
    return { url, method, headers };
}

// Async function with await
async function fetchWithRetry(url, retries = 3) {
    for (let i = 0; i < retries; i++) {
        try {
            const response = await fetch(url);
            return response.json();
        } catch (err) {
            if (i === retries - 1) throw err;
        }
    }
}

// Generator function wrapping (deferred but should not crash)
function* idGenerator() {
    let id = 0;
    while (true) {
        yield id++;
    }
}

// Regular function expression as callback param — should NOT be captured as symbol
const result = [1, 2, 3].map(function double(x) {
    return x * 2;
});

// IIFE — should NOT be captured
const config = (function() {
    return { env: 'production', debug: false };
})();

// Arrow IIFE — should NOT be captured
const theme = (() => {
    return { primary: 'blue', secondary: 'gray' };
})();

// Class with get/set, static, private fields (stage 3)
class ModernClass {
    #privateField = 42;

    constructor(value) {
        this.publicField = value;
    }

    get value() {
        return this.#privateField + this.publicField;
    }

    set value(v) {
        this.publicField = v;
    }

    static fromJSON(json) {
        return new ModernClass(json.publicField);
    }

    static get DEFAULT_VALUE() {
        return 100;
    }

    #privateMethod() {
        return this.#privateField;
    }

    publicMethod() {
        return this.#privateMethod();
    }
}

// Export with re-naming
export { ModernClass as Modern };

// Named export: function
export async function fetchData(url) {
    const resp = await fetch(url);
    return resp.json();
}

// Named export: class
export class ExportedService {
    serve() { return 'serving'; }
}

// Named export: arrow const
export const STATUS_CODES = {
    OK: 200,
    NOT_FOUND: 404,
    ERROR: 500,
};

// Note: STATUS_CODES is NOT a function, just a value — should NOT be captured

// Top-level import statement (should not produce symbols)
import { readFile } from 'fs';
import express from 'express';
