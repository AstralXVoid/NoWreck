package samples.generics;

import java.util.List;
import java.util.Map;

/** Generic classes, bounded parameters, wildcards, generic methods. */
public class Box<T extends Comparable<T>> {
    private T value;

    public Box(T value) {
        this.value = value;
    }

    public T get() {
        return value;
    }

    public <U> U map(U input) {
        return input;
    }

    public <K, V> Map<K, V> pair(K key, V val) {
        return null;
    }

    public List<? extends Number> numbers() {
        return null;
    }

    public List<? super Integer> sink() {
        return null;
    }

    public static <E> Box<E> of(E value) {
        return new Box<>(value);
    }
}

class Registry<K extends Comparable<K>, V> extends Box<K> {
    private V payload;

    Registry(K key, V value) {
        super(key);
        this.payload = value;
    }

    <A, B> void put(A a, B b) {
        payload = null;
    }
}
