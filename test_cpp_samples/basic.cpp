// basic.cpp — the core declaration shapes.

#include <string>

int counter = 0;

namespace app
{
    class Greeter
    {
    public:
        Greeter(const std::string& name) : name_(name) {}

        std::string greet() const
        {
            return format(name_);
        }

    protected:
        std::string format(const std::string& value) const;

    private:
        std::string name_;
    };

    enum class Mode
    {
        Fast,
        Slow
    };

    using Name = std::string;

    int run(Mode mode)
    {
        return dispatch(mode);
    }
}

int free_function(int value)
{
    return value + 1;
}
