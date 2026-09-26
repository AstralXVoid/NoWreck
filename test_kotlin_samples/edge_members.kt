package samples.members

class Full(val value: Int, private val name: String) {
    val computed: Int = derive()

    var mutable: String = "start"
        get() = field
        set(value) {
            field = value.trim()
        }

    init {
        initialise()
    }

    constructor(other: Full) : this(other.value, other.name) {
        copied()
    }

    fun derivedValue(): Int = value + 1

    private fun helper(): Int = assist()

    open fun openMethod() {}

    internal fun internalMethod() = internalWork()
}

class Generic<T : Comparable<T>>(val items: List<T>) {
    fun largest(): T {
        return items.max()
    }
}

abstract class Base {
    abstract fun required(): Int

    open fun optional(): Int = baseWork()
}
