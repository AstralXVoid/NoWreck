// edge_strings.cpp — literals and comments must invent nothing.

// void ghost(int) { phantom(); }
/* int hidden() { return 1; } */

const char* kBlocked = "not_a_call() and { unbalanced }";

class Report
{
public:
    std::string render(int value)
    {
        std::string text = format(value);
        print_line("call me maybe()");
        print_line(R"(raw { text } here)");
        print_line(u8"prefixed");
        char marker = '}';
        comment_only();
        /* ignore(); */
        // ignore_too();
        (void)marker;
        return text;
    }

    std::string format(int value) const;
};

void print_line(const char* text)
{
    consume(text);
}
