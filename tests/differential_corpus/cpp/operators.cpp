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
