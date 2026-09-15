// Dimension: control flow must not be mistaken for declaration heads.
// - ``if``/``for``/``while``/``switch``/``catch``/``synchronized`` heads
//   end in ``) {`` exactly like a method header.
// - A semicolon inside a ``for`` header is not a statement boundary.
// - ``try``/``finally``/``else``/``do``/``static`` have no paren group.
// - Labels (``outer:``) and switch arrows (``case X ->``) are not heads.
// - Calls inside every construct belong to the enclosing method.

package com.example.control;

public class Control {
    void branches(boolean flag, int count) {
        if (flag) {
            enable();
        } else if (count > 0) {
            disable();
        } else {
            fallback();
        }
    }

    void loops(int limit) {
        for (int i = 0; i < limit; i++) {
            step(i);
        }
        while (limit > 0) {
            limit = decrement(limit);
        }
        do {
            limit--;
        } while (limit > 0);
    }

    void forEachLoop(int[] values) {
        for (int value : values) {
            step(value);
        }
    }

    void labelled() {
        outer:
        for (int i = 0; i < 3; i++) {
            for (int j = 0; j < 3; j++) {
                if (check(i, j)) {
                    continue outer;
                }
            }
        }
    }

    void switches(int value) {
        switch (value) {
            case 1:
                first();
                break;
            default:
                other();
        }
    }

    void arrowSwitch(int value) {
        switch (value) {
            case 10 -> tenth();
            default -> {
                other();
            }
        }
    }

    void guarded(int value) {
        synchronized (this) {
            guard();
        }
        try {
            risky();
        } catch (IllegalStateException | IllegalArgumentException e) {
            recover(e);
        } finally {
            cleanup();
        }
    }

    static void enable() {
    }

    static void disable() {
    }

    static void fallback() {
    }

    static void step(int value) {
    }

    static int decrement(int value) {
        return value - 1;
    }

    static boolean check(int a, int b) {
        return a == b;
    }

    static void first() {
    }

    static void other() {
    }

    static void tenth() {
    }

    static void guard() {
    }

    static void risky() {
    }

    static void recover(Exception e) {
    }

    static void cleanup() {
    }
}
