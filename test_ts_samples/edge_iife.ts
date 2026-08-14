// IIFE patterns for TypeScript — should all be excluded
const config = (function(): Record<string, number> {
    return { value: 42 };
})();

const theme = ((): Record<string, string> => {
    return { mode: "dark" };
})();

(function(): void {
    console.log("standalone IIFE");
})();

void function(): void {
    console.log("void IIFE");
}();

var oldStyle = (function(): number {
    return 1;
})();

// Positive controls — these SHOULD be captured
const normalArrow = (): void => {
    return;
};

function normalFunc(): void {
    return;
}
