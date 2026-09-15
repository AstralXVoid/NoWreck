// Dimension: the core model — a class with fields, a constructor and
// methods.  No top-level functions exist in Java, so every callable is a
// METHOD with a parent class; fields are class-shell content, never
// symbols.

package com.example.basic;

import java.util.List;

public class Greeter {
    private final String prefix;
    private int calls;

    public Greeter(String prefix) {
        this.prefix = prefix;
    }

    public String greet(String name) {
        calls += 1;
        return prefix + name;
    }

    public String shout(String name) {
        return greet(name).toUpperCase();
    }

    public int callCount() {
        return calls;
    }

    static Greeter defaultGreeter() {
        return new Greeter("hi ");
    }

    private void unused(List<String> items) {
        for (String item : items) {
            trim(item);
        }
    }

    private String trim(String value) {
        return value.trim();
    }
}
