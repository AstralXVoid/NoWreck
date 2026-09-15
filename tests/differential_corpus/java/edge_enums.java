// Dimension: enums (probe J11).
// - Enum constants are class-shell content, never symbols.
// - An enum constant with a class body (``FAST(1) { … }``) has exactly the
//   shape of a package-private constructor — it must not become a method,
//   and its members must not become symbols.  Its methods ARE callers.
// - Constructor args on constants (``FAST(1)``) are not calls.
// - Enum members after the ``;`` separator are ordinary members: the
//   constructor and methods are METHOD symbols and their calls count.

package com.example.enums;

public enum Mode {
    FAST(1) {
        @Override
        int weight() {
            return scale(base());
        }
    },
    SLOW(2) {
        @Override
        int weight() {
            return base() / 2;
        }
    },
    AUTO(0) {
        @Override
        int weight() {
            return detect();
        }
    };

    private final int rank;

    Mode(int rank) {
        this.rank = rank;
    }

    abstract int weight();

    int base() {
        return rank * 10;
    }

    int scale(int value) {
        return value + offset();
    }

    int offset() {
        return rank;
    }

    static int detect() {
        return 1;
    }
}
