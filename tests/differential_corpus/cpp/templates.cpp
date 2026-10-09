// templates.cpp — function, class, alias and specialised templates.

template <typename T>
T identity(T value)
{
    return value;
}

template <class T>
struct Box
{
    T value_;

    T get() const
    {
        return value_;
    }

    void put(T next)
    {
        value_ = next;
    }
};

template <>
struct Box<int>
{
    int value_;
};

template <typename T>
using Stack = Box<T>;

int use_templates()
{
    Box<int> box;
    box.put(identity<int>(7));
    return box.get();
}
