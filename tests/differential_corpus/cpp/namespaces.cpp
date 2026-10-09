// namespaces.cpp — namespaces, nested namespaces and qualified calls.

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

int dispatch()
{
    int a = app::helper();
    int b = app::detail::deep();
    int c = ::hidden();
    return a + b + c;
}
