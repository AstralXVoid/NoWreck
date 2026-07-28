// Test case 2: Arrow functions assigned to variables

// Simple arrow function
const greet = (name) => {
    console.log("Hello, " + name);
};

// Arrow function with implicit return (no braces)
const double = (x) => x * 2;

// Arrow function with single param (no parens)
const square = x => x * x;

// Arrow function assigned via let
let counter = () => {
    let count = 0;
    return count++;
};

// Arrow function via var (legacy)
var oldStyle = () => {
    return "legacy";
};

// Not an arrow function — regular function expression assigned to var
// (This should NOT be captured as an arrow function symbol)
var regularFunc = function() {
    return "regular";
};
