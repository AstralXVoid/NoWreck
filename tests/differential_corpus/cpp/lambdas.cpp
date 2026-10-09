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
