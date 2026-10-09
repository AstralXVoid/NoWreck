// greeter.cpp — the free-function definitions.

#include "greeter.h"

namespace purecpp
{
    std::string trimCopy(const std::string& text)
    {
        std::string copy = text;
        copy.erase(copy.find_last_not_of(" \t\n"));
        return copy;
    }

    std::string formatGreeting(const std::string& name)
    {
        return "Hello, " + trimCopy(name) + "!";
    }

    std::string greet(const std::string& name)
    {
        return formatGreeting(name);
    }

    std::string farewell(const std::string& name)
    {
        return "Goodbye, " + trimCopy(name) + "!";
    }
}
