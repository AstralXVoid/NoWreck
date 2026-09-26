package samples.basic

typealias Handler = (Int) -> Unit

interface Greeter {
    fun greet(name: String): String
}

class Person(val name: String, val age: Int) {
    fun birthday(): Int {
        return age + 1
    }
}

enum class Color {
    RED,
    GREEN,
    BLUE
}

fun topLevel(value: Int): Int {
    return value * 2
}
