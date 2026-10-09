// basic.cpp — free functions, a forward declaration and simple calls.

int add(int a, int b);

int add(int a, int b)
{
    return a + b;
}

int scale(int value)
{
    return multiply(value, 2);
}

int multiply(int a, int b)
{
    int product = a * b;
    return product;
}
