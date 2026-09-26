// Dimension: enum classes — constants, a constructor with arguments, a
// companion, and entry bodies.  An enum is an ENUM symbol, a companion's
// method belongs to the *enum* (probe K3), and an entry body's methods are
// not symbols while still being callers (probe K11).

package com.example.enums

enum class Status {
    ACTIVE,
    INACTIVE,
    UNKNOWN,
}

enum class Level(val weight: Int) {
    LOW(1),
    MEDIUM(5),
    HIGH(10);

    fun describe(): String = label(weight)

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
    PLAIN;

    open fun name(): String = "kind"
}

enum class Direction {
    NORTH,
    SOUTH,
    EAST,
    WEST;

    fun opposite(): Direction = Direction.values()[0]

    fun label(): String = name.lowercase()
}

private fun label(weight: Int): String = "level-$weight"

private fun lookup(weight: Int): Level = Level.LOW

private fun entryWork(): String = "work"
