package purejava;

import java.util.ArrayList;
import java.util.List;

public class Calculator {
    private final List<Double> history = new ArrayList<>();

    public Calculator() {
    }

    public double add(double a, double b) {
        double result = a + b;
        history.add(result);
        return result;
    }

    public double subtract(double a, double b) {
        double result = a - b;
        history.add(result);
        return result;
    }

    public double multiply(double a, double b) {
        double result = a * b;
        history.add(result);
        return result;
    }

    public double divide(double a, double b) {
        double result = a / b;
        history.add(result);
        return result;
    }

    public void display() {
        for (double val : history) {
            System.out.println(val);
        }
    }

    public static double computeAverage(double[] values) {
        double sum = 0.0;
        for (double v : values) {
            sum += v;
        }
        return sum / values.length;
    }
}
