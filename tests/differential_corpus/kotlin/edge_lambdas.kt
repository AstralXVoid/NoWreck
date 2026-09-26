// Dimension: lambdas and higher-order functions — trailing lambdas,
// anonymous functions, function-typed parameters, function-valued
// properties and local lambdas.  A function-valued property owns the calls
// in its lambda (probe K6); a bare lambda belongs to the nearest enclosing
// named caller.

package com.example.lambdas

val topLevelLambda = { value: Int -> value + 1 }

val topLevelAnonymous = fun(value: Int): Int = value * 2

val plainValue = 41

fun applyTwice(value: Int, transform: (Int) -> Int): Int {
    return transform(transform(value))
}

fun trailingLambda(items: List<Int>): Int {
    var total = 0
    items.forEach { item ->
        total += item
    }
    items.map { it + 1 }
    return total
}

fun lambdaArguments(items: List<Int>): Int {
    return items.fold(0) { acc, item -> acc + scale(item) }
}

fun anonymousFunction(value: Int): Int {
    val doubler = fun(x: Int): Int = x * 2
    return doubler(value)
}

fun localLambda(): Int {
    val local = { n: Int -> localWork(n) }
    return local(1)
}

fun returningLambda(): (Int) -> Int {
    return { value -> scale(value) }
}

fun inlineWork(items: List<Int>): Int {
    return items.filter { it > 1 }.map { it * 2 }.count()
}

class LambdaHolder {
    val field = { y: Int ->
        fieldWork()
        y * 2
    }

    val anonField = fun(): Int {
        return anonFieldWork()
    }

    val computed = compute()

    fun useLocals(): Int {
        val local = { n: Int -> localWork(n) }
        return local(1)
    }
}

private fun scale(value: Int): Int = value * 3

private fun localWork(value: Int): Int = value + 1

private fun fieldWork(): Int = 1

private fun anonFieldWork(): Int = 2

private fun compute(): Int = 3
