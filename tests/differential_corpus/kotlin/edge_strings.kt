// Dimension: strings — plain templates, `${…}` interpolation (which holds
// real calls, probe K7), raw strings, escapes and char literals.  None of
// this may invent a symbol, and only the interpolation may add a call.

package com.example.strings

fun stringShapes(name: String, count: Int): String {
    val plain = "plain text"
    val simple = "hello $name"
    val computed = "total: ${count + 1}"
    val formatted = "value is ${format(count)}"
    val escaped = "quote: \" and backslash: \\"
    val char = 'x'
    val dollar = "cost: ${count} dollars"
    val raw = """
        line one
        line two $name
        line three ${format(count)}
    """.trimIndent()
    return plain + simple + computed + formatted + escaped + char + dollar + raw
}

class StringHolder(private val prefix: String) {
    fun describe(value: Int): String = "$prefix: ${format(value)}"

    fun empty(): String = ""

    fun blank(): String = "   "

    fun nested(count: Int): String {
        val inner = format(count)
        return "outer ${inner.trim()}"
    }
}

fun pathLike(): String {
    val url = "https://example.com/a//b"
    return url.trim()
}

private fun format(value: Int): String = value.toString()
