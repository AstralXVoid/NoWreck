// Dimension: generics (probe J8).
// - Type parameters on classes and methods are content; name extraction
//   excludes the ``<…>`` region.
// - Generic receiver chains ``Box<String>``, wildcards ``? extends T`` and
//   bounded params are all transparent to call extraction.
// - ``Util.<String>parse(x)`` (explicit call type arguments) is a call —
//   the checker must not read it as a declaration head.
// - A generic constructor ``Foo(T item)`` is a package-private-shaped head
//   with a type parameter.

package com.example.generics;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class Store<K extends Comparable<K>, V> {
    private final Map<K, V> entries;
    private final List<V> history = new ArrayList<>();

    public Store(Map<K, V> entries) {
        this.entries = entries;
    }

    public V get(K key) {
        return entries.get(key);
    }

    public List<V> historyFrom(int index) {
        return history.subList(index, history.size());
    }

    public <R> R map(K key, Mapper<K, V, R> mapper) {
        return mapper.apply(key, entries.get(key));
    }

    public static <T> T identity(T value) {
        return value;
    }

    public static <T extends Comparable<T>> T max(T left, T right) {
        return left.compareTo(right) >= 0 ? left : right;
    }

    void explicitTypeArgument() {
        Store.<String>identity("x");
    }

    void wildcards(List<? extends Number> numbers, List<? super Integer> sink) {
        numbers.size();
        sink.clear();
    }

    static class Pair<A, B> {
        private final A first;
        private final B second;

        Pair(A first, B second) {
            this.first = first;
            this.second = second;
        }

        A first() {
            return first;
        }

        B second() {
            return second;
        }
    }
}

interface Mapper<K, V, R> {
    R apply(K key, V value);
}
