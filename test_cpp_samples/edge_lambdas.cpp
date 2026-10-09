// edge_lambdas.cpp — named and unnamed lambdas.

auto doubler = [](int value)
{
    return scale(value);
};

int apply_all(int value)
{
    auto local = [&](int inner) {
        return doubler(inner) + offset();
    };
    auto immediate = [](int seed) {
        return seed;
    }(value);
    return local(value) + immediate;
}

int offset()
{
    return 3;
}
