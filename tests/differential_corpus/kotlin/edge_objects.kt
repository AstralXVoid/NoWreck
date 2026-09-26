// Dimension: objects — `object` singletons, `data object`, companions
// (named and unnamed), and object *expressions*.  An object is a CLASS
// symbol, a companion is not a symbol but its members belong to the outer
// class (probe K3), and an object expression's methods are callers with no
// parent class while never being symbols (probe K11).

package com.example.objects

object Registry {
    private val entries = mutableMapOf<String, Int>()

    fun register(key: String, value: Int): Unit {
        entries[key] = value
    }

    fun lookup(key: String): Int {
        return entries.getValue(key)
    }
}

data object Singleton {
    fun describe(): String = "singleton"
}

class Service(val repo: Repository) {
    companion object {
        fun create(): Service {
            return Service(Repository())
        }

        fun empty(): Service = create()
    }

    fun run(): Unit {
        val writer = repo.writer
        writer.flush()
    }
}

class Named {
    companion object Factory {
        fun make(): Named = Named()
    }
}

class Holder {
    object Helpers {
        fun help(): Int {
            return assist()
        }
    }

    fun use(): Int {
        return Helpers.help()
    }
}

fun anonymousObject(): Int {
    val runnable = object : Runnable {
        override fun run(): Unit {
            anonWork()
        }
    }
    runnable.run()
    return 0
}

class Repository {
    val writer: Writer = Writer()
}

class Writer {
    fun flush(): Unit = Unit
}

private fun assist(): Int = 1

private fun anonWork(): Unit = Unit
