// Dimension: records (probe J6 plus the compact-constructor node).
// - ``record_declaration`` → CLASS (it is a class-like type).
// - A **compact constructor** ``Point { … }`` is
//   ``compact_constructor_declaration`` — a METHOD named after the record
//   whose calls are attributed to it.
// - A canonical constructor and a static factory are ordinary METHODs.
// - Accessor methods declared explicitly and a nested type are handled
//   like any other member.

package com.example.records;

public record Point(int x, int y) {
    private static final int ORIGIN = 0;

    Point {
        validate(x, y);
    }

    Point(String encoded) {
        this(decodeX(encoded), decodeY(encoded));
    }

    static Point origin() {
        return new Point(ORIGIN, ORIGIN);
    }

    int manhattan() {
        return Math.abs(x) + Math.abs(y);
    }

    String describe() {
        return "(" + x + "," + y + ")";
    }

    static int decodeX(String encoded) {
        return encoded.length();
    }

    static int decodeY(String encoded) {
        return encoded.isEmpty() ? 0 : encoded.hashCode();
    }

    static void validate(int x, int y) {
        check(x);
        check(y);
    }

    static void check(int value) {
        if (value < 0) {
            reject();
        }
    }

    static void reject() {
        throw new IllegalArgumentException("negative");
    }

    record Bounds(Point low, Point high) {
        boolean contains(Point p) {
            return inside(p);
        }

        boolean inside(Point p) {
            return p.manhattan() >= low.manhattan();
        }
    }
}
