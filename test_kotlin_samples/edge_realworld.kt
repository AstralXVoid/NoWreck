package samples.realworld

import kotlin.math.max

typealias Logger = (String) -> Unit

@Serializable
data class User(val name: String, val age: Int)

interface Repository {
    fun find(name: String): User?
    fun save(user: User)
}

sealed interface Result<out T> {
    fun value(): T
}

class InMemoryRepository(private val logger: Logger) : Repository {
    private val users = mutableMapOf<String, User>()

    companion object {
        fun empty(): InMemoryRepository {
            return InMemoryRepository { message -> defaultLog(message) }
        }
    }

    init {
        preload()
    }

    constructor(seed: List<User>) : this({ message -> seedLog(message) }) {
        seed.forEach { user -> save(user) }
    }

    override fun find(name: String): User? = users[name]

    override fun save(user: User) {
        logger("saving ${user.name}")
        users[user.name] = user
        notifyChanged()
    }

    fun youngerThan(age: Int): List<User> {
        return users.values.filter { it.age < age }
    }

    fun oldestAge(): Int {
        return users.values.maxOfOrNull { it.age } ?: 0
    }
}

enum class Status {
    ACTIVE,
    SUSPENDED;

    fun describe(): String = name.lowercase()
}

fun String.initials(): String = this.split(" ").map { it.first() }.joinToString("")

fun process(users: List<User>, logger: Logger): Int {
    var count = 0
    users.forEach { user ->
        logger(user.name)
        count = max(count, user.age)
    }
    return count
}

fun main() {
    val repository = InMemoryRepository.empty()
    repository.save(User("Ada", 36))
    process(repository.youngerThan(40), { message -> println(message) })
}
