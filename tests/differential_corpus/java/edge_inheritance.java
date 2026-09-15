// Dimension: inheritance and abstract types.
// - ``extends`` / ``implements`` clauses are content, not calls/symbols.
// - ``super.m()`` and ``super(args)`` behave per J1: the first is a call,
//   the second is an explicit_constructor_invocation (keyword-excluded).
// - An abstract method is a METHOD symbol with a body-less ``;`` head.
// - An anonymous subclass of an abstract type produces no symbol; its
//   overriding method is a caller.
// - Overrides keep the same name as the supertype method (name sets are
//   shared, which is fine — the audit compares names).

package com.example.inheritance;

import java.util.List;

abstract class Shape {
    private final String label;

    Shape(String label) {
        this.label = label;
    }

    abstract double area();

    String describe() {
        return label;
    }
}

class Circle extends Shape {
    private final double radius;

    Circle(double radius) {
        super("circle");
        this.radius = radius;
    }

    @Override
    double area() {
        return scale(radius);
    }

    double scale(double value) {
        return value * value * Math.PI;
    }

    String report() {
        return super.describe() + area();
    }
}

class Region extends Shape implements Comparable<Region> {
    private final List<Shape> shapes;

    Region(List<Shape> shapes) {
        super("region");
        this.shapes = shapes;
    }

    @Override
    double area() {
        return total();
    }

    @Override
    public int compareTo(Region other) {
        return Double.compare(area(), other.area());
    }

    double total() {
        double sum = 0;
        for (Shape shape : shapes) {
            sum += shape.area();
        }
        return sum;
    }

    Shape anonymous() {
        return new Shape("anon") {
            @Override
            double area() {
                return computeArea();
            }
        };
    }

    static double computeArea() {
        return 0;
    }
}
