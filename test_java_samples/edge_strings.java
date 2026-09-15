package samples.strings;

/** String escapes, character literals and text blocks. */
public class StringShapes {
    private String plain = "plain";
    private char letter = 'x';
    private char newline = '\n';
    private char escapedQuote = '\'';
    private char unicode = '\u0041';
    private String escaped = "line\n\ttab \"quoted\" back\\slash";
    private String unicodeString = "\u00e9";
    private String block = """
            first
            second
            """;
    private String emptyBlock = """
            """;

    public String describe() {
        return plain + escaped + block + emptyBlock + letter + newline
                + escapedQuote + unicode + unicodeString;
    }

    public String join(String a, String b) {
        return a + ":" + b;
    }
}
