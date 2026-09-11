// Basic module: functions, defaults, arrow functions, module-level call.

const PREFIX = "app";

function greet(name, excited = false) {
  const message = `${PREFIX}: ${name}`;
  if (excited) {
    return message.toUpperCase();
  }
  return message;
}

function sum(values) {
  let total = 0;
  for (const value of values) {
    total += value;
  }
  return total;
}

const double = (x) => x * 2;

function* range(start, end) {
  for (let i = start; i < end; i += 1) {
    yield i;
  }
}

const result = sum([1, 2, 3]);