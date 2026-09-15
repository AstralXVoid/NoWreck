package samples.negatives;

import java.util.function.Supplier;

/** Constructs that must NOT become symbols. */
public class Negatives {
    public static final int CONSTANT = 1;
    private String field;

    void withLocals() {
        int local = 1;
        Supplier<Integer> lambda = () -> local;
        class LocalClass {
            void localMethod() {
            }
        }
        Runnable anon = new Runnable() {
            @Override
            public void run() {
                field = null;
            }
        };
        anon.run();
        lambda.get();
        new LocalClass();
    }
}

enum Constants {
    A, B, C;

    void method() {
    }
}

@interface Elements {
    String value();
}

record Component(int x, int y) {
}
