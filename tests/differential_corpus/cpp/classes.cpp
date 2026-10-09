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

// A tagged declaration wraps the specifier in a ``declaration``: the type
// (and its members) still have to be indexed.
struct Tagged
{
    void touch() { poke(); }
} instance;

// A nested type member wraps the specifier in a ``field_declaration``, and
// its methods are symbols of the nested type.
struct Outer
{
    struct Inner
    {
        void visit() { ping(); }
    };

    enum Kind { First, Second };

    int field;
};

// A forward declaration has no body but is still a CLASS fact.
struct Forwarded;

void local_scope()
{
    // A local type is not a symbol, and neither are its members — its
    // calls are still attributed to the local method as the caller.
    struct Local
    {
        void hidden() { unseen(); }
    };
    (void)0;
}
