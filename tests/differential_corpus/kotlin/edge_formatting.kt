// Dimension: formatting variety — wrapped parameter lists, multi-line
// expression bodies, trailing commas, blank lines, block and line comments,
// and optional semicolons.  Kotlin drops optional semicolons in the
// grammar (probe K10), so none of this may change a symbol or a call.

/*
 * A block comment mentioning things that look like declarations:
 *     fun notReal() { }
 * and calls that look real: ghostCall()
 */

package com.example.formatting

import java.util.Locale

fun wrapped(
    first: Int,
    second: Int,
    third: Int,
): Int {
    return combine(first, second) + third
}

fun multiLine(
    items: List<Int>
): Int =
    items
        .map { value -> scale(value) }
        .sum()

class Formatted(
    val name: String,
    private val locale: Locale = Locale.US,
    val tags: List<String> = emptyList(),
) {
    val summary: String
        get() = render()

    fun render(): String {
        val lowered = name.lowercase(locale);
        return lowered.trim()
    }

    fun describe(
        prefix: String,
        suffix: String,
    ): String = prefix + name + suffix
}

fun semicolons(): Int {
    val a = 1; val b = 2;
    return a + b
}

private fun combine(first: Int, second: Int): Int = first + second

private fun scale(value: Int): Int = value * 2
