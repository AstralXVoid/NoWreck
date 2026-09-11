// Interfaces, enums, type aliases — TS-only symbol kinds.

interface Point {
  x: number;
  y: number;
}

interface Shape {
  area(): number;
  describe(): string;
}

interface Named {
  readonly name: string;
}

enum Color {
  Red = "red",
  Green = "green",
  Blue = "blue",
}

enum StatusCode {
  Ok = 200,
  NotFound = 404,
}

type Id = string;

type Callback = (value: number) => void;

type Maybe<T> = T | null;

interface WithDefault extends Shape, Named {
  z?: number;
}

function render(shape: Shape): string {
  return shape.describe();
}