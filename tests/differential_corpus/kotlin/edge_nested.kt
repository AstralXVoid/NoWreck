// Dimension: nesting — nested and inner classes, companions, and local
// declarations.  A nested class is a real symbol and its members belong to
// the *inner* class; a local class inside a method is not a symbol but is
// still a caller (probe K1/K11).

package com.example.nested

class Outer {
    private val label = "outer"

    class StaticNested {
        fun staticMethod(): Int = 1
    }

    inner class Inner {
        fun innerMethod(): String = label + "!"
    }

    companion object {
        fun create(): Outer = Outer()

        val NAME: String = "outer"
    }

    fun outerMethod(): Int {
        val nested = StaticNested()
        return nested.staticMethod()
    }
}

class Container {
    private val items = mutableListOf<String>()

    class Entry(val key: String)

    companion object Factory {
        fun make(): Container = Container()
    }

    fun add(entry: Entry): Unit {
        items.add(entry.key)
    }

    fun localWork(): Int {
        class Local {
            fun method(): Int = localHelper()
        }
        return Local().method()
    }
}

class Deep {
    class Middle {
        class Leaf {
            fun leafMethod(): Int = 3
        }

        fun middleMethod(): Int = Leaf().leafMethod()
    }

    fun deepMethod(): Int {
        return Middle().middleMethod()
    }
}

object Nested {

    class Inside {
        fun insideMethod(): Int = 4
    }

    fun holder(): Int {
        return Inside().insideMethod()
    }
}

private fun localHelper(): Int = 1
