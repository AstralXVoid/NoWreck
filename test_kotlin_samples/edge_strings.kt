package samples.strings

fun stringShapes(name: String, count: Int): String {
    val plain = "plain text"
    val simple = "hello $name"
    val computed = "total: ${count + 1}"
    val char = 'x'
    val raw = """
        line one
        line two $name
    """.trimIndent()
    return plain + simple + computed + char + raw
}

class StringHolder {
    fun describe(value: Int): String = "value is ${format(value)}"

    fun empty(): String = ""
}
