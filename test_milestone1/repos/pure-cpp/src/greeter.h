// greeter.h — the free-function declarations.

#ifndef PURE_CPP_GREETER_H
#define PURE_CPP_GREETER_H

#include <string>

namespace purecpp
{
    std::string trimCopy(const std::string& text);

    std::string formatGreeting(const std::string& name);

    std::string greet(const std::string& name);

    std::string farewell(const std::string& name);
}

#endif
