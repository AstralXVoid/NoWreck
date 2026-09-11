// Edge: ambient declarations, namespaces, overloads.

declare function ambientFn(x: number): number;

declare const AMBIENT_CONST: string;

declare class AmbientClass {
  method(): void;
}

namespace Geometry {
  export interface Point {
    x: number;
    y: number;
  }

  export function distance(a: Point, b: Point): number {
    return Math.hypot(a.x - b.x, a.y - b.y);
  }

  export class Circle {
    constructor(public radius: number) {}

    area(): number {
      return Math.PI * this.radius * this.radius;
    }
  }
}

function overloaded(input: string): string;
function overloaded(input: number): number;
function overloaded(input: string | number): string | number {
  return input;
}

function useAmbient(): number {
  return ambientFn(3) + AMBIENT_CONST.length;
}