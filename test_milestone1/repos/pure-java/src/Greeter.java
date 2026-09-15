package purejava;

public class Greeter {
    public static String greet(String name) {
        return formatGreeting(name);
    }

    public static String formatGreeting(String name) {
        String trimmed = name.trim();
        return "Hello, " + trimmed + "!";
    }

    public static String farewell(String name) {
        return "Goodbye, " + name + "!";
    }
}
