package samples.objects

object Registry {
    fun lookup(key: String): Int {
        return register(key)
    }
}

data object Singleton

class Service(val repo: Repo) {
    companion object {
        fun create(): Service {
            return Service(Repo())
        }

        val NAME = "service"
    }

    fun run() {
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
}

fun anonymousObject() {
    val runnable = object : Runnable {
        override fun run() {
            anonWork()
        }
    }
    runnable.run()
}
