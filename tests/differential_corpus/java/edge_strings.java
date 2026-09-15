// Dimension: comment and literal stripping (probe J7).
// - A ``//`` inside a string must not start a comment, and a quote inside
//   a comment must not start a string.
// - Text blocks (``"""``) are multi-line leaf nodes; code-looking text
//   inside them must not produce symbols or calls.
// - Char literals, escapes and a trailing line continuation inside a text
//   block are all stripped without unbalancing the source.
// - Javadoc is a block comment.

package com.example.strings;

/** A Javadoc block comment with class String and a call helper() inside. */
public class Strings {
    private static final String URL = "https://example.com/v1/get";
    private static final String SLASHES = "a // b";
    private static final String QUOTES = "she said \"def helper():\"";
    private static final char QUOTE = '\'';
    private static final char SLASH = '/';
    private static final char NEWLINE = '\n';

    private static final String BLOCK = """
            class Fake {
                void fakeMethod() { helper(); }
            }
            // not a comment in here
            /* not a comment either */
            """;

    private static final String CONTINUED = """
            line one \
            line two helper() still text
            """;

    public String build() {
        String first = URL + SLASHES + QUOTES;
        String second = first.replace("/", "_");
        return second + BLOCK + CONTINUED + QUOTE + SLASH + NEWLINE;
    }

    public String helper() {
        return "helper";
    }
}
