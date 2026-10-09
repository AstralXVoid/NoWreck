// negatives.cpp — shapes that must NOT become symbols or calls.

int (*callback)(int);

using Callback = int (*)(int);

int counter = seed();

class Holder
{
public:
    Holder();

private:
    int limit_ = threshold();
    static const int kBase = 4;
};

enum class Kind
{
    First = pick(),
    Second = 2
};

void guarded()
{
    int local = helper();
    auto sized = sizeof(int);
    auto other = static_cast<int>(local);
    (void)sized;
    (void)other;
    (void)callback;
    (void)counter;
}
