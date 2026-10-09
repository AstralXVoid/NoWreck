// preprocessor.cpp — directives, macro definitions and conditional bodies.

#include <vector>

#define TRACE(x) LOG(x)
#define LIMIT (16)

void run_pipeline(int value)
{
#ifdef ENABLE_TRACE
    trace_value(value);
#else
    quiet_value(value);
#endif

#if defined(SANITIZE)
    sanitize();
#endif

    int doubled = value * 2;
    (void)doubled;
}

int total()
{
    return accumulate();
}
