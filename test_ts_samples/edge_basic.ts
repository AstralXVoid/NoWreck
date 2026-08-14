// Core positive patterns for TypeScript scanning
function hello(name: string): string {
    return "Hello, " + name;
}

const world = (x: number): number => {
    return x + 1;
};

class MyClass {
    greet(name: string): void {
        console.log(name);
    }
}
