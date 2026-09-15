package samples.interfaces;

/** Interface constants, abstract members, defaults, statics and privates. */
public interface Greeter {
    String GREETING = "hi";

    String name();

    default String greet() {
        return GREETING + " " + name();
    }

    static Greeter of(final String n) {
        return () -> n;
    }

    private String helper() {
        return "h";
    }
}

interface Extended extends Greeter {
    int count();

    default int doubled() {
        return count() * 2;
    }
}
