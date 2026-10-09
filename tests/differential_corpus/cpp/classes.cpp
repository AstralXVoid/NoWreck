// classes.cpp — inline definitions, constructors, destructors and fields.

class Counter
{
public:
    Counter() : count_(0) {}

    ~Counter() {}

    void increment()
    {
        count_ = count_ + 1;
    }

    int value() const
    {
        return count_;
    }

private:
    int count_;
};

struct Point
{
    double x;
    double y;
};

union Value
{
    int as_int;
    double as_double;
};
