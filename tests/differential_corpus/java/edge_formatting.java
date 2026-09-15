// Dimension: formatting variety — the checker classifies *statements*
// between brace boundaries, so none of this changes the extract.
// - Allman braces (the body brace on its own line).
// - One-line bodies (``void m() { step(); }``) and empty bodies.
// - Blank lines, trailing comments and inconsistent indentation.
// - A wrapped argument list in a *call* (not in a declaration header).
// - Nested one-line declarations on a single line.

package com.example.formatting;

public class Formatting
{
    private int counter = 0;

    void allman()
    {
        reset();
        step();
    }

    void sameLine() { reset(); step(); }

    void empty() {}

    void blankLines()


    {
        reset();


        step();
    }

    void wrappedCall() {
        combine(
            first(),
            second()
        );
    }

    void nestedOneLiners() { helper(); class Sneaky { void inner() { deep(); } } new Sneaky().inner(); }

    void trailingComments() { reset(); // reset first
        step(); /* then step */
    }

    static void reset() { }

    static void step() { }

    static void combine(String a, String b) { }

    static String first() { return "a"; }

    static String second() { return "b"; }

    static void helper() { }

    static void deep() { }
}
