// Dimension: things that must NOT be captured.
// - A field initializer call has no caller → not a call.
// - A lambda in a field initializer has no caller → its calls are not
//   calls either.
// - A static/instance initializer block is not a caller.
// - A constructor invocation ``new Foo()`` is an object_creation_expression.
// - An array initializer and an annotation argument are not calls.
// - A call in a method head position (``func(`` inside a declaration head)
//   is not a call.
// - A class literal ``Foo.class`` is not a symbol and not a call.

package com.example.negatives;

import java.util.List;
import java.util.function.Supplier;

@SuppressWarnings("unused")
public class Negatives {
    private static final String SEED = literal();

    private final int size = compute();

    private final Supplier<String> supplier = () -> produce();

    private final int[] table = {1, 2, 3};

    static {
        bootstrap();
    }

    {
        instanceInit();
    }

    private String name;

    String unusedFieldAccess() {
        return null;
    }

    String withDeclaredCalls(String value) {
        return trim(value);
    }

    void creation() {
        Negatives other = new Negatives();
        Object klass = Negatives.class;
        other.getClass();
    }

    static String literal() {
        return "seed";
    }

    static int compute() {
        return 1;
    }

    static String produce() {
        return "p";
    }

    static void bootstrap() {
    }

    void instanceInit() {
    }

    String trim(String value) {
        return value.trim();
    }
}
