// Dimension: call shapes (probe J1/J2/J3).
// - bare foo(), obj.foo(), this.foo(), super.foo() captured.
// - A.B.foo() (field_access receiver) and a[0].bar() (array_access)
//   captured — every receiver except a call resolves to the final name.
// - f().bar() (receiver is itself a method_invocation) excluded.
// - new Foo() is an object_creation_expression, NOT a call (J2).
// - Foo::bar is a method_reference, NOT a call (J3).
// - new Foo().bar() IS captured: its receiver is a creation, not a call.

package com.example.calls;

import java.util.List;

class Base {
    String tag() {
        return "base";
    }
}

class Calls extends Base {
    private final List<String> items = List.of("a");
    private final Helper helper = new Helper();

    String bare() {
        return tag();
    }

    String member() {
        return helper.compute();
    }

    String onThis() {
        return this.tag();
    }

    String onSuper() {
        return super.tag();
    }

    String qualified() {
        return Helper.describe();
    }

    String onArray() {
        return items.get(0).trim();
    }

    String stringReceiver() {
        return "literal".trim();
    }

    String callReceiver() {
        return helper.compute().trim();
    }

    String groupedReceiver() {
        return (helper.compute()).trim();
    }

    String constructorReceiver() {
        return new Helper().compute();
    }

    String genericReceiver() {
        return new Box<String>("x").value();
    }

    String usesMethodReference() {
        return items.stream().map(String::trim).findFirst().orElse("");
    }

    void chained() {
        helper.compute().trim().toLowerCase();
    }
}

class Helper {
    String compute() {
        return "computed";
    }

    static String describe() {
        return "described";
    }
}

class Box<T> {
    private final T payload;

    Box(T payload) {
        this.payload = payload;
    }

    T value() {
        return payload;
    }
}
