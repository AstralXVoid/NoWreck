package samples.enums

enum class Status {
    ACTIVE,
    INACTIVE;
}

enum class Level(val weight: Int) {
    LOW(1),
    HIGH(10);

    fun describe(): String = label()

    companion object {
        fun fromWeight(weight: Int): Level {
            return lookup(weight)
        }
    }
}

enum class Kind {
    SIMPLE {
        override fun name(): String {
            return entryWork()
        }
    },
    OTHER;

    open fun name(): String = "kind"
}

class Container {
    enum class Nested {
        ONE,
        TWO
    }

    fun useNested(): Int {
        return Nested.ONE.ordinal
    }
}
