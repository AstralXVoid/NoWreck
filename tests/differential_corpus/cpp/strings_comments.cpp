// strings_comments.cpp — literals and comments must invent nothing.

// void ghost(int) { phantom(); }
/* int hidden() { return 1; } */

const char* kBlocked = "not_a_call() and { unbalanced }";

void shout()
{
    print_line("call me maybe()");
    print_line(R"(raw { text } here)");
    print_line(u8"prefixed");
    char marker = '}';
    comment_only();
    /* ignore(); */
    // ignore_too();
    (void)marker;
}

void print_line(const char* text)
{
    consume(text);
}
