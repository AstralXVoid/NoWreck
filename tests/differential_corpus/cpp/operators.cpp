// operators.cpp — operator declarations and definitions.

struct Vec
{
    Vec operator+(const Vec& other) const
    {
        return combine(other);
    }

    Vec& operator+=(const Vec& other)
    {
        return absorb(other);
    }

    Vec operator[](int index) const;

    void operator()();
};

Vec Vec::operator*(const Vec& other) const
{
    return scale_by(other);
}

// A conversion operator is an ``operator_cast`` in the grammar; its body is
// class API the change detector has to see.  ``merge`` is a reference-return
// declaration-only member: its declarator is a ``reference_declarator`` that
// exposes no ``declarator`` field.
struct Mask
{
    explicit operator bool() const
    {
        return ready();
    }

    Mask& merge(const Mask& other);
};
