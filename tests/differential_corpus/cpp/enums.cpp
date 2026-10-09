// enums.cpp — unscoped and scoped enumerations.

enum Color
{
    RED,
    GREEN,
    BLUE
};

enum class Mode : int
{
    On = 1,
    Off = 0
};

enum class Empty
{
};

Color pick(Mode mode)
{
    if (mode == Mode::On)
    {
        return RED;
    }
    return GREEN;
}
