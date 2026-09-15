// Dimension: anonymous functions (the JS/TS arrow rule generalised).
// - A lambda is NOT a caller: calls inside it attribute to the nearest
//   enclosing named method, so they still count.
// - A lambda block body ``x -> { … }`` must not open a caller body, and
//   must not be mistaken for a method head.
// - An anonymous-class method IS a caller (its calls count) and produces
//   no symbol.
// - A method reference ``Foo::bar`` is not a call (J3); a call inside a
//   lambda argument to ``forEach`` is.

package com.example.lambdas;

import java.util.List;
import java.util.function.Function;
import java.util.function.Supplier;

public class Functional {
    private final List<String> items = List.of("a", "b");

    void expressionLambda() {
        items.forEach(item -> log(item));
    }

    void blockLambda() {
        items.forEach(item -> {
            String upper = normalize(item);
            log(upper);
        });
    }

    void nestedLambdas() {
        Supplier<Function<String, String>> factory = () -> value -> decorate(value);
        factory.get().apply("x");
    }

    String composed(Function<String, String> first, Function<String, String> second) {
        return first.andThen(second).apply("v");
    }

    void methodReferences() {
        items.forEach(this::log);
        items.stream().map(String::trim).forEach(this::log);
        items.removeIf(String::isEmpty);
    }

    void anonymousClass() {
        Runnable task = new Runnable() {
            @Override
            public void run() {
                execute();
            }
        };
        task.run();
    }

    void anonymousWithCapture() {
        Range range = new Range() {
            @Override
            public boolean includes(int value) {
                return matches(value);
            }
        };
        range.includes(3);
    }

    void fieldLambdaIsNotACaller() {
        Runnable later = () -> schedule();
        later.run();
    }

    static void log(String value) {
        value.length();
    }

    static String normalize(String value) {
        return value.trim();
    }

    static String decorate(String value) {
        return "[" + value + "]";
    }

    static void execute() {
        log("x");
    }

    static boolean matches(int value) {
        return value > 0;
    }

    static void schedule() {
        execute();
    }

    interface Range {
        boolean includes(int value);
    }
}
