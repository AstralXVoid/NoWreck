// Stress test: large file with many symbols and mixed patterns

// Utility functions
function identity(x) { return x; }
function noop() {}
function constant(value) { return () => value; }
function compose(f, g) { return (x) => f(g(x)); }
function pipe(...fns) { return (x) => fns.reduce((v, fn) => fn(v), x); }

// Math utilities
function add(a, b) { return a + b; }
function subtract(a, b) { return a - b; }
function multiply(a, b) { return a * b; }
function divide(a, b) { return a / b; }
function clamp(value, min, max) { return Math.max(min, Math.min(max, value)); }

// Validation functions
function isString(value) { return typeof value === 'string'; }
function isNumber(value) { return typeof value === 'number'; }
function isBoolean(value) { return typeof value === 'boolean'; }
function isArray(value) { return Array.isArray(value); }
function isObject(value) { return value !== null && typeof value === 'object' && !Array.isArray(value); }
function isFunction(value) { return typeof value === 'function'; }

// Arrow function utilities
const map = (fn) => (arr) => arr.map(fn);
const filter = (pred) => (arr) => arr.filter(pred);
const reduce = (fn, initial) => (arr) => arr.reduce(fn, initial);
const flatten = (arr) => arr.reduce((acc, val) => acc.concat(val), []);
const unique = (arr) => [...new Set(arr)];
const chunk = (arr, size) => {
    const result = [];
    for (let i = 0; i < arr.length; i += size) {
        result.push(arr.slice(i, i + size));
    }
    return result;
};

// Data model classes
class User {
    constructor(id, name, email) {
        this.id = id;
        this.name = name;
        this.email = email;
    }

    getDisplayName() {
        return this.name;
    }

    getEmailDomain() {
        return this.email.split('@')[1];
    }

    validate() {
        return this.email.includes('@') && this.name.length > 0;
    }

    toJSON() {
        return { id: this.id, name: this.name, email: this.email };
    }
}

class Admin extends User {
    constructor(id, name, email, role) {
        super(id, name, email);
        this.role = role;
    }

    hasPermission(permission) {
        return this.role === 'admin' || this.role === 'superadmin';
    }
}

class Product {
    constructor(sku, name, price) {
        this.sku = sku;
        this.name = name;
        this.price = price;
    }

    getPriceWithTax(taxRate) {
        return this.price * (1 + taxRate);
    }

    isAffordable() {
        return this.price < 100;
    }
}

class Cart {
    constructor() {
        this.items = [];
    }

    add(product) {
        this.items.push(product);
    }

    remove(sku) {
        this.items = this.items.filter(item => item.sku !== sku);
    }

    getTotal() {
        return this.items.reduce((sum, item) => sum + item.price, 0);
    }

    clear() {
        this.items = [];
    }

    getCount() {
        return this.items.length;
    }
}

// Service classes
class ApiService {
    static create(baseUrl) { return new ApiService(baseUrl); }

    constructor(baseUrl) {
        this.baseUrl = baseUrl;
    }

    async get(path) { return this._request('GET', path); }
    async post(path, data) { return this._request('POST', path, data); }
    async put(path, data) { return this._request('PUT', path, data); }
    async delete(path) { return this._request('DELETE', path); }

    async _request(method, path, data) {
        const response = await fetch(this.baseUrl + path, {
            method,
            body: data ? JSON.stringify(data) : undefined,
            headers: { 'Content-Type': 'application/json' },
        });
        return response.json();
    }
}

class LoggerService {
    constructor(prefix) { this.prefix = prefix; }
    info(msg) { console.log(`[INFO][${this.prefix}] ${msg}`); }
    warn(msg) { console.warn(`[WARN][${this.prefix}] ${msg}`); }
    error(msg) { console.error(`[ERROR][${this.prefix}] ${msg}`); }
}

// Empty classes for edge testing
class ConfigStore {}
class EventBus {}
class CacheManager {}

// Exported patterns
export function exportedUtil() { return 'util'; }
export class ExportedClass {
    method() { return 'method'; }
    static staticMethod() { return 'static'; }
}
export const exportedArrow = () => 'arrow';

// Named exports alongside
export { identity, noop, clamp };
