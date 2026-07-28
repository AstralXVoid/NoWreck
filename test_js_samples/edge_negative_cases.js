// Edge case 9: Various non-captured patterns (negative tests)

// Regular function expression assigned to a variable (NOT arrow) — should NOT be captured
const regularFuncExpr = function() {
    return "regular";
};

// IIFE — should NOT be captured
(function() {
    console.log("IIFE");
})();

// Arrow function used as callback — should NOT be captured
[1, 2, 3].map(x => x * 2);

// Arrow function in object literal — should NOT be captured as a symbol
const obj = {
    method: () => {},
    regular: function() {}
};

// Immediately-invoked arrow — should NOT be captured
(() => {
    console.log("iife arrow");
})();

// Nested arrow in a non-captured position
const pipeline = [1, 2, 3]
    .filter(x => x > 1)
    .map(x => x * 2);

// Arrow function passed as argument
setTimeout(() => {
    console.log("timeout");
}, 100);

// Promise callback
Promise.resolve().then(() => {
    console.log("then");
});
