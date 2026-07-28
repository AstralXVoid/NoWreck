// Edge case 5: Classes with getters/setters and static methods
class FullFeatured {
    constructor(value) {
        this._value = value;
    }

    get value() {
        return this._value;
    }

    set value(v) {
        this._value = v;
    }

    static createDefault() {
        return new FullFeatured(42);
    }

    static get DEFAULT() {
        return 42;
    }

    regularMethod() {
        return this._value;
    }
}

// Getters/setters at top level in a class expression (not declaration)
const ObjWithGetters = {
    get x() { return 1; },
    set x(v) { /* noop */ }
};

// Class expression assigned to const
const MyClassExpr = class {
    method() {}
};
