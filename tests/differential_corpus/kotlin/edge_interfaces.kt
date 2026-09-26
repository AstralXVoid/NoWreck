// Dimension: interfaces — plain, `fun interface`, `sealed interface`, and
// interfaces with default method bodies.  All of them are INTERFACE
// symbols (probe K2: `fun interface` carries the `interface` token, so it
// is an interface, not a function), and a default body's calls belong to
// the interface method.

package com.example.interfaces

interface Plain {
    fun required(): Int
}

fun interface Sam {
    fun only(value: Int): Int
}

sealed interface Shape {
    fun area(): Double

    fun describe(): String {
        return format(area())
    }
}

interface WithDefaults {
    fun provided(): Int {
        return helper()
    }

    fun alsoProvided(): String = format(provided().toDouble())

    val computed: Int
        get() = provided() + 1
}

interface Comparable2<T> {
    fun compareWith(other: T): Int

    fun isGreaterThan(other: T): Boolean = compareWith(other) > 0
}

class Impl : Plain {
    override fun required(): Int {
        return 7
    }
}

class Square(val side: Double) : Shape {
    override fun area(): Double = side * side
}

private fun format(value: Double): String = value.toString()

private fun helper(): Int = 42
