// Dimension: interfaces (probe J6/J9).
// - ``interface_declaration`` → INTERFACE; ``@interface``
//   (``annotation_type_declaration``) → INTERFACE as well.
// - Abstract methods (``String value();``) are METHOD symbols — the only
//   body-less callables in the corpus.
// - ``default`` and ``static`` methods carry bodies and are callers.
// - Annotation type elements are NOT symbols (the grammar emits
//   ``annotation_type_element_declaration``, not ``method_declaration``).

package com.example.interfaces;

public interface Repository<T> {
    T find(String id);

    void save(T entity);

    String describe();

    default String summary(String id) {
        return describe() + format(id);
    }

    static <E> Repository<E> empty() {
        return null;
    }

    private String format(String id) {
        return decorate(id);
    }

    private String decorate(String id) {
        return "[" + id + "]";
    }
}

interface Marker {
    String NAME = "marker";

    boolean isEmpty();
}

@interface Tagged {
    String value();

    int priority() default 0;
}
