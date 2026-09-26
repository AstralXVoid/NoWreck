// Dimension: the negatives — things that must NOT become symbols or calls.
// Class-level property initialisers, `init` blocks and annotation
// arguments own no calls (probe K11); a member dunder call is excluded
// while a bare `__dunder__()` call is not; `@Annotation(...)` argument
// parens are not call parens; and a local `fun`/class is not a symbol.

package com.example.negatives

@Suppress("UNUSED_PARAMETER")
class Negatives {
    val initialised: Int = compute()

    val annotated: String = "value"

    init {
        preload()
    }

    fun dunderMember(value: Helper): Unit {
        value.__secret__()
    }

    fun bareDunder(): Unit {
        __bare__()
    }

    fun constructorCall(): Unit {
        val helper = Helper()
        helper.use()
    }

    fun tagged(name: String): Int {
        @Suppress("UNUSED")
        val length = name.length
        return length
    }

    fun infixPair(value: Int): Pair<Int, Int> {
        return value to value
    }

    fun localDeclarations(): Int {
        fun local(value: Int): Int {
            return localWork(value)
        }
        class Local {
            fun method(): Int = localHelper()
        }
        return local(Local().method())
    }

    fun classLiteral(): String {
        return Negatives::class.java.name
    }
}

class Helper {
    fun use(): Unit = Unit

    fun __secret__(): Unit = Unit
}

@Target(AnnotationTarget.CLASS)
annotation class Marker(val priority: Int)

@Marker(priority = 1)
class Annotated

private fun compute(): Int = 1

private fun preload(): Unit = Unit

private fun __bare__(): Unit = Unit

private fun localWork(value: Int): Int = value

private fun localHelper(): Int = 1
