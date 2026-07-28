// Calculator module.

class Calculator {
  add(a, b) {
    return a + b;
  }

  subtract(a, b) {
    return a - b;
  }

  multiply(a, b) {
    var result = a * b;
    console.log("multiply(" + a + ", " + b + ") = " + result);
    return result;
  }

  divide(a, b) {
    if (b === 0) {
      throw new Error("Cannot divide by zero");
    }
    return a / b;
  }
}

function computeAverage(values) {
  var total = sum(values);
  var count = len(values);
  return total / count;
}
