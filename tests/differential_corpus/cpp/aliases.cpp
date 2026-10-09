// aliases.cpp — using aliases, typedefs and using-declarations.

using Count = unsigned long;

using Handler = Count (*)(int);

typedef int Legacy;

typedef void (*Callback)(int);

typedef int Table[4];

using namespace std;

Count apply(Handler handler, Count value)
{
    return handler(value);
}

Callback make()
{
    return nullptr;
}
