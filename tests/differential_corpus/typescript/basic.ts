// Basic module: typed functions, arrow functions, generics on functions.

const BASE_URL = "https://api.example.com";

function greet(name: string, excited = false): string {
  const message = `${BASE_URL}: ${name}`;
  if (excited) {
    return message.toUpperCase();
  }
  return message;
}

function sum(values: number[]): number {
  let total = 0;
  for (const value of values) {
    total += value;
  }
  return total;
}

function identity<T>(value: T): T {
  return value;
}

const double = (x: number): number => x * 2;

function* range(start: number, end: number): Generator<number> {
  for (let i = start; i < end; i += 1) {
    yield i;
  }
}

const total = sum([1, 2, 3]);