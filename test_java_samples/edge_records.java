package samples.records;

/** Records (compact + canonical constructors), sealed types. */
public record Point(int x, int y) {
    public Point {
        if (x < 0) {
            throw new IllegalArgumentException("x");
        }
    }

    public Point(int x) {
        this(x, 0);
    }

    public int sum() {
        return x + y;
    }

    public static Point origin() {
        return new Point(0, 0);
    }
}

sealed interface Shape permits Circle, Square {
    double area();
}

record Circle(double radius) implements Shape {
    public double area() {
        return 3.14 * radius * radius;
    }
}

final class Square implements Shape {
    private final double side;

    Square(double side) {
        this.side = side;
    }

    public double area() {
        return side * side;
    }
}
