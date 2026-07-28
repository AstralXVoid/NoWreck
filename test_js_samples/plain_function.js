// Test case 1: Plain function declaration
function greet(name) {
    console.log("Hello, " + name);
}

// Another function declaration with default params
function calculateTotal(price, tax = 0.1) {
    return price * (1 + tax);
}

// Function with no params
function getTimestamp() {
    return Date.now();
}
