// edge_grammar_lag.cpp — a numeric user-defined literal is a grammar error,
// so the scanner must warn loudly and still extract partial symbols.

class Config
{
public:
    Config();

    int name() const
    {
        return 1;
    }
};

void broken()
{
    auto h = 1"_km";
}
