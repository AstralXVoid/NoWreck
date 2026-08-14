// Negative test: TypeScript-only constructs that must NOT be captured
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
