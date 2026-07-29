// v4: IIFE patterns — explicitly excluded (Gap 3)

// 1. IIFE assigned to const (function expression)
const config = (function() {
    return { env: 'production', debug: false };
})();

// 2. IIFE assigned to const (arrow)
const theme = (() => {
    return { primary: 'blue', secondary: 'gray' };
})();

// 3. Standalone IIFE (no assignment)
(function() {
    const internal = 'hidden';
    console.log(internal);
})();

// 4. Standalone arrow IIFE (no assignment)
(() => {
    const x = 42;
    console.log(x);
})();

// 5. Void IIFE
void function() {
    const msg = 'void iife';
    console.log(msg);
}();

// 6. Void arrow IIFE
void (() => {
    console.log('void arrow iife');
})();

// 7. Positive control: regular arrow function (MUST be captured)
const normalArrow = () => {
    return 'captured';
};

// 8. Positive control: regular function declaration (MUST be captured)
function normalFunction() {
    return 'captured';
}

// 9. IIFE assigned via var
var legacyConfig = (function() {
    return { legacy: true };
})();

// 10. Nested IIFE (const inside a function body — should not affect top-level)
function container() {
    const innerConfig = (function() {
        return { nested: true };
    })();
    return innerConfig;
}
