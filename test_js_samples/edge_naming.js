// Edge case 6: Various naming edge cases
// Unicode identifiers (valid JS)
const π = Math.PI;
const πSquared = () => π * π;

// Very long name
const thisIsAnExtremelyLongFunctionNameThatNobodyWouldActuallyUseInPractice = () => {
    return "long";
};

// Name with underscores and dollars
const _privateHelper = () => {};
const $getValue = () => {};

// Symbol names that could be confusing
function Function() {}  // Same name as constructor
function Symbol() {}    // Same name as built-in

// Name collision scenario
function process() {}
function process() {}  // Duplicate name, same file
