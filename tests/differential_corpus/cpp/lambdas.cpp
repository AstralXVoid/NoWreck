// lambdas.cpp — named and unnamed lambdas.

auto doubler = [](int value)
{
    return scale(value);
};

int apply_all(int value)
{
    auto local = [&](int inner) {
        return doubler(inner) + offset();
    };
    return local(value);
}

int offset()
{
    return 3;
}

// A class-field lambda is a caller named after the field (never a symbol),
// exactly like a JS class-field arrow: its calls must be attributed.
struct Hooks
{
    auto on_ready = []()
    {
        return notify();
    };
};
