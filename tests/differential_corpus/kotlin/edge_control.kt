// Dimension: control flow — `if`, `when`, `for`, `while`, `try`/`catch`/
// `finally`, and the null-safety operators.  None of these is a call, so
// every keyword must be filtered and no branch may invent a name.

package com.example.control

import java.io.IOException

fun classify(value: Int): String {
    if (value > 0) {
        return positive()
    } else if (value < 0) {
        return negative()
    }
    return "zero"
}

fun describe(value: Any?): String {
    when (value) {
        is String -> return value.trim()
        is Int -> return value.toString()
        null -> return "null"
        else -> return "other"
    }
}

fun loop(items: List<Int>): Int {
    var total = 0
    for (item in items) {
        total += item
    }
    var index = 0
    while (index < items.size) {
        total += items[index]
        index += 1
    }
    do {
        total -= 1
    } while (total > 100)
    return total
}

fun guarded(path: String): String {
    try {
        val text = read(path)
        return text.trim()
    } catch (error: IOException) {
        report(error)
        return ""
    } finally {
        cleanup()
    }
}

fun nullSafe(value: String?): Int {
    val safe = value ?: "fallback"
    val length = value?.length
    return safe.length + (length ?: 0)
}

private fun positive(): String = "positive"

private fun negative(): String = "negative"

private fun read(path: String): String = path

private fun report(error: IOException): Unit = error.message

private fun cleanup(): Unit = Unit

private fun cleanupExtra(): Unit {
    val items = listOf(1, 2, 3)
    items.forEach { item ->
        if (item > 1) {
            report(IOException("boom"))
        }
    }
}
