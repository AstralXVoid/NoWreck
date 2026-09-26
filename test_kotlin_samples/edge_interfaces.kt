package samples.interfaces

interface Plain {
    fun required(): Int
}

fun interface Sam {
    fun only(x: Int): Int
}

sealed interface Shape {
    fun area(): Double
}

interface WithDefaults {
    fun provided(): Int {
        return helper()
    }

    fun alsoProvided(): String = format()
}

class Impl : Plain {
    override fun required(): Int {
        return 7
    }
}
