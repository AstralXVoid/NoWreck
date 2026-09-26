// Dimension: class members — primary and secondary constructors, `init`
// blocks, property accessors, visibility modifiers and expression bodies.
// A secondary constructor is a METHOD named after its class (the Kotlin
// spelling of Java's constructor rule) and an accessor owns the calls in
// its body, while an `init` block and a class-level initialiser own none
// (probe K11, the Java-family rule).

package com.example.members

class Full(
    val value: Int,
    private val name: String,
    internal val tag: String = "default",
) {
    val computed: Int = derive()

    var mutable: String = "start"
        get() = normalise(field)
        set(newValue) {
            field = newValue.trim()
        }

    private val lazyValue: Int by lazy { computeLazy() }

    init {
        initialise()
    }

    constructor(other: Full) : this(other.value, other.name, other.tag) {
        copied()
    }

    constructor(value: Int) : this(value, "unnamed") {
        copied()
    }

    fun derivedValue(): Int = value + 1

    private fun helper(): Int = assist()

    protected open fun openMethod(): Unit = Unit

    internal fun internalMethod(): Int = internalWork()

    companion object {
        const val DEFAULT_TAG = "default"

        fun create(value: Int): Full = Full(value)

        fun empty(): Full {
            return create(0)
        }
    }
}

class Minimal {
    fun only(): Int = 1
}

abstract class Base {
    abstract fun required(): Int

    open fun optional(): Int = baseWork()
}

private fun derive(): Int = 1

private fun normalise(text: String): String = text.trim()

private fun computeLazy(): Int = 2

private fun initialise(): Unit = Unit

private fun copied(): Unit = Unit

private fun assist(): Int = 3

private fun internalWork(): Int = 4

private fun baseWork(): Int = 5
