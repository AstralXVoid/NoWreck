// Dimension: annotations (probe J4).
// - Annotations are *children* of the declaration they decorate (under a
//   ``modifiers`` node), so an annotation edit is part of that
//   declaration's own body hash — no sibling folding is needed.
// - An annotation's argument parens are NOT calls (the parser emits an
//   ``annotation`` node).  Annotation arguments are constant expressions,
//   so a call can never legally appear inside them.
// - Annotations on a method make the declaration start on the annotation's
//   line (the node's start_point), which the multiround suite pins
//   separately; the differential compares names, not lines.

package com.example.annotations;

import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Deprecated
@SuppressWarnings("unchecked")
public class Annotated {
    @Deprecated
    private String legacy = "legacy";

    @SafeVarargs
    static <T> void consume(T... values) {
        inspect(values);
    }

    @Deprecated
    @SuppressWarnings({"rawtypes", "unchecked"})
    public String render(@Deprecated int count) {
        return format(count);
    }

    void localAnnotation() {
        @SuppressWarnings("unused")
        String scratch = template();
        use(scratch);
    }

    static String template() {
        return "t";
    }

    static String format(int count) {
        return String.valueOf(count);
    }

    static void inspect(Object[] values) {
        values.getClass();
    }

    static void use(String value) {
        value.length();
    }

    @Target(ElementType.METHOD)
    @interface Marker {
        String name() default "";
    }
}
