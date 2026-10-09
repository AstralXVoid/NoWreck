// edge_templates.cpp — function, class, alias and specialised templates.

template <typename T>
T maximum(T left, T right)
{
    return compare(left, right) ? left : right;
}

template <class T, int Size>
class Buffer
{
public:
    T read(int index) const
    {
        return data_[index];
    }

    void write(int index, T value);

private:
    T data_[Size];
};

template <>
class Buffer<char, 0>
{
public:
    char read(int index) const
    {
        return fallback(index);
    }
};

template <typename T>
using Ptr = T*;

template <typename T>
T forwarding(T value)
{
    return maximum<T>(value, clone(value));
}
