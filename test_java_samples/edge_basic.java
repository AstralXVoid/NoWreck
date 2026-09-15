// Core Java constructs — all should be captured as symbols.

package samples.basic;

public class Greeter {
    private final String prefix;
    private int uses;

    public Greeter(String prefix) {
        this.prefix = prefix;
        this.uses = 0;
    }

    public String greet(String name) {
        uses++;
        return prefix + ", " + name + "!";
    }

    public int getUses() {
        return uses;
    }

    public static Greeter defaultGreeter() {
        return new Greeter("Hello");
    }
}

interface Drawable {
    void draw();
}

enum Direction {
    NORTH, SOUTH, EAST, WEST
}

record UserId(long value) {
}
