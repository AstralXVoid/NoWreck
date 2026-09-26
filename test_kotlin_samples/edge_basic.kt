package samples.edge

// Extension functions: FUNCTION with no parent_class (probe K4).
fun String.shout(): String = this.uppercase()

fun <T> List<T>.secondOrNull(): T? = this.getOrNull(1)

fun Int.doubled(): Int {
    return this * 2
}

// Local functions are callers but never symbols (probe K1).
fun withLocal(): Int {
    fun inner(x: Int): Int {
        return x + 1
    }
    return inner(1)
}

// Nested classes are real symbols; their methods attribute to the inner.
class Outer {
    class Inner {
        fun innerMethod(): Int {
            return 1
        }
    }

    fun host(): Int {
        class Local {
            fun localMethod(): Int {
                return localWork()
            }
        }
        return Local().localMethod()
    }
}
