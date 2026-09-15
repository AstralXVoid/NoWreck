package samples.annotations;

import java.util.List;

/** Annotations on classes, fields, methods and parameters. */
@Deprecated
public class Annotated {
    @SuppressWarnings("unused")
    private int counter;

    @Override
    public String toString() {
        return "Annotated";
    }

    @SafeVarargs
    public final <T> void varargs(List<T>... lists) {
        counter = lists.length;
    }

    @Deprecated
    @SuppressWarnings({"a", "b"})
    public void multiAnnotated() {
    }

    public void paramAnnotated(@Deprecated int x) {
        counter = x;
    }
}

@FunctionalInterface
interface Action {
    void run();
}

@interface Config {
    String name();
}
