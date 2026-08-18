// TypeScript-only constructs — captured as INTERFACE / TYPE_ALIAS / ENUM
// since v0.8.0 (previously a negative test asserting they were NOT captured).
// Members (method signatures, enum members) are structural detail and are
// intentionally NOT captured.
interface User {
    name: string;
    age: number;
}

type Status = "active" | "inactive";

enum Color {
    Red,
    Green,
    Blue,
}

// Positive controls nearby — these SHOULD be captured
function workingFunction(): void {
    return;
}

class WorkingClass {
    method(): void {}
}

const workingArrow = (): void => {
    return;
};
