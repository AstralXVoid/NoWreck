// edge_namespaces.cpp — namespaces, nested namespaces and extern "C".

namespace app
{
    int helper()
    {
        return 1;
    }

    namespace detail
    {
        int deep()
        {
            return helper();
        }
    }
}

namespace
{
    int hidden()
    {
        return 2;
    }
}

extern "C"
{
    int c_entry(int value)
    {
        return hidden() + value;
    }
}

int dispatch()
{
    int a = app::helper();
    int b = app::detail::deep();
    int c = ::hidden();
    int d = c_entry(a);
    return a + b + c + d;
}
