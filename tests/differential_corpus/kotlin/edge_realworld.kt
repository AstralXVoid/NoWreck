// Dimension: a realistic file — a repository interface, an in-memory
// implementation with a companion factory, an init block, an extension
// function, a data class, a sealed result type and a `main`-style flow.
// It mixes every boundary in one file, which is where a checker's
// approximations meet the parser's real behaviour.

package com.example.realworld

typealias LogSink = (String) -> Unit

@JvmInline
value class UserId(val raw: String)

data class User(val id: UserId, val name: String, val age: Int)

sealed class Outcome {
    data class Ok(val user: User) : Outcome()

    data class Err(val reason: String) : Outcome()
}

interface UserRepository {
    fun find(id: UserId): User?

    fun save(user: User)
}

class InMemoryUserRepository(private val log: LogSink) : UserRepository {
    private val users = mutableMapOf<UserId, User>()

    companion object {
        fun withDefaults(): InMemoryUserRepository {
            return InMemoryUserRepository { message -> defaultLog(message) }
        }
    }

    init {
        preload()
    }

    constructor(seed: List<User>) : this({ message -> seedLog(message) }) {
        seed.forEach { user -> save(user) }
    }

    override fun find(id: UserId): User? = users[id]

    override fun save(user: User) {
        log("saving ${user.name}")
        users[user.id] = user
        notifyChanged()
    }

    fun youngerThan(age: Int): List<User> {
        return users.values.filter { it.age < age }
    }

    fun oldestAge(): Int {
        return users.values.maxOfOrNull { it.age } ?: 0
    }

    fun describe(user: User): String = user.describe()

    private fun notifyChanged(): Unit = Unit

    private fun preload(): Unit = preload()
}

fun User.describe(): String = "$name (${age})"

fun String.initials(): String = this.split(" ").map { it.first() }.joinToString("")

fun load(repository: UserRepository, id: UserId): Outcome {
    val user = repository.find(id)
    return if (user == null) {
        Outcome.Err("missing")
    } else {
        Outcome.Ok(user)
    }
}

fun report(outcomes: List<Outcome>): Int {
    var failures = 0
    outcomes.forEach { outcome ->
        when (outcome) {
            is Outcome.Ok -> println(outcome.user.describe())
            is Outcome.Err -> failures += 1
        }
    }
    return failures
}

fun main() {
    val repository = InMemoryUserRepository.withDefaults()
    repository.save(User(UserId("1"), "Ada", 36))
    val loaded = load(repository, UserId("1"))
    println(report(listOf(loaded)))
    println("Ada Lovelace".initials())
}

private fun preload(): Unit = Unit

private fun defaultLog(message: String): Unit = println(message)

private fun seedLog(message: String): Unit = println(message)
