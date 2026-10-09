// calculator.cpp — the calculator class definitions.

#include "calculator.h"

namespace purecpp
{
    Calculator::Calculator(double seed)
    {
        history_.push_back(seed);
    }

    double Calculator::add(double a, double b)
    {
        double result = a + b;
        history_.push_back(result);
        return result;
    }

    double Calculator::subtract(double a, double b)
    {
        double result = a - b;
        history_.push_back(result);
        return result;
    }

    double Calculator::multiply(double a, double b)
    {
        double result = a * b;
        history_.push_back(result);
        return result;
    }

    double Calculator::divide(double a, double b)
    {
        double result = a / b;
        history_.push_back(result);
        return result;
    }

    void Calculator::display() const
    {
        for (double value : history_)
        {
            print_value(value);
        }
    }

    double Calculator::computeAverage(const std::vector<double>& values)
    {
        return totalOf(values) / values.size();
    }
}
