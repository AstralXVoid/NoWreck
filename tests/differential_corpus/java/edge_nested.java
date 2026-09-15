// Dimension: nesting (probe J10).
// - Nested classes/interfaces/enums are their own symbols.
// - A member method's parent_class is the IMMEDIATE enclosing type (the
//   differential compares names only, but the shapes must agree).
// - A local class inside a method body and an anonymous class body
//   produce NO symbols — members of a method body are not members of the
//   enclosing type.  Their methods are still callers.

package com.example.nested;

public class Outer {
    private final Inner inner = new Inner();

    public String run() {
        return inner.work();
    }

    class Inner {
        String work() {
            return helper();
        }

        String helper() {
            return "inner";
        }
    }

    static class Nested {
        static String build() {
            return Inner2.make();
        }
    }

    class Inner2 {
        static String make() {
            return "made";
        }
    }

    interface Policy {
        String apply(String value);
    }

    enum Kind {
        SIMPLE
    }

    void withLocalClass() {
        class Local {
            void run() {
                deep();
            }

            void deep() {
                deeper();
            }

            void deeper() {
                nothing();
            }
        }
        new Local().run();
    }

    void withAnonymousClass() {
        Policy policy = new Policy() {
            @Override
            public String apply(String value) {
                return transform(value);
            }
        };
        policy.apply("x");
    }

    String transform(String value) {
        return value;
    }

    void nothing() {
    }
}
