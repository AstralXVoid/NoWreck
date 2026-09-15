package samples.enums;

/** Enums with bodies, constructors and methods; annotation types. */
public enum Planet {
    MERCURY(3.3e23, 2.4e6),
    EARTH(5.97e24, 6.37e6);

    private final double mass;
    private final double radius;

    Planet(double mass, double radius) {
        this.mass = mass;
        this.radius = radius;
    }

    public double surfaceGravity() {
        return 6.67e-11 * mass / (radius * radius);
    }

    public static Planet heaviest() {
        return EARTH;
    }
}

enum Status {
    ACTIVE, INACTIVE
}

@interface Marker {
    String value() default "x";

    int priority() default 0;
}
