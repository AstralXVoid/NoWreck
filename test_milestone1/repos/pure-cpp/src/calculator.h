// calculator.h — the calculator class declaration.

#ifndef PURE_CPP_CALCULATOR_H
#define PURE_CPP_CALCULATOR_H

#include <vector>

namespace purecpp
{
    class Calculator
    {
    public:
        explicit Calculator(double seed);

        double add(double a, double b);
        double subtract(double a, double b);
        double multiply(double a, double b);
        double divide(double a, double b);

        void display() const;

        static double computeAverage(const std::vector<double>& values);

    private:
        std::vector<double> history_;
    };
}

#endif
