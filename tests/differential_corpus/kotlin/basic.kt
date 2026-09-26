// Dimension: the core model — a class with a primary constructor,
// properties and methods, plus top-level functions (which Kotlin supports
// and Java does not, so a top-level `fun` is a FUNCTION with no parent,
// never a METHOD).

package com.example.basic

import kotlin.math.abs

private const val DEFAULT_PREFIX = "hi "

fun greet(name: String): String = formatGreeting(name)

fun formatGreeting(name: String): String {
    val trimmed = name.trim()
    return DEFAULT_PREFIX + trimmed
}

fun farewell(name: String): String {
    return "Goodbye, " + name
}

class Greeter(private val prefix: String) {
    private var calls: Int = 0

    fun greet(name: String): String {
        calls += 1
        return prefix + name
    }

    fun shout(name: String): String {
        return greet(name).uppercase()
    }

    fun callCount(): Int = calls

    fun reset(): Unit {
        calls = 0
    }
}

class Distance(private val meters: Double) {
    fun absolute(): Double {
        return abs(meters)
    }

    fun plus(other: Distance): Distance {
        return Distance(meters + other.meters)
    }
}
