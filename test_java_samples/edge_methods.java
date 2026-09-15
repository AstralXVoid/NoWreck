package samples.methods;

import java.util.List;

/** Every method modifier shape, plus overloads and multi-line signatures. */
public abstract class MethodShapes {
    public static final int MAX = 10;

    public abstract void abstractMethod();

    public final void finalMethod() {
        System.out.println(MAX);
    }

    public static void staticMethod() {
        finalMethodName();
    }

    public synchronized void syncMethod() {
    }

    public native void nativeMethod();

    public void varargs(String... parts) {
        consume(parts);
    }

    public <T> T generic(T value) {
        return value;
    }

    public void overloaded() {
    }

    public void overloaded(int x) {
        overloaded();
    }

    public String[] arrayReturn() {
        return new String[0];
    }

    public List<String> genericReturn() {
        return null;
    }

    protected void multiLine(
            int first,
            String second
    ) {
        System.out.println(first + second);
    }

    MethodShapes() {
    }

    MethodShapes(int x) {
        this();
    }

    private static void finalMethodName() {
    }

    private void consume(String[] parts) {
    }
}
