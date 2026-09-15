package samples;

/** Basic Java constructs — every declaration should be captured. */
public class Basic {
    private String name;

    public Basic(String name) {
        this.name = name;
    }

    public String greet() {
        return "Hello, " + name + "!";
    }

    public static int add(int a, int b) {
        return a + b;
    }
}

interface Shape {
    double area();
}

enum Color {
    RED, GREEN, BLUE
}

record Point(int x, int y) {
}
