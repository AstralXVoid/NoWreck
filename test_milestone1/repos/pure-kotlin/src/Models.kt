package purekotlin

data class User(val name: String, val age: Int) {
    fun display(): String = "$name: $age"

    fun toDict(): String = "{\"name\": \"$name\", \"age\": $age}"
}

class AdminUser(name: String, age: Int, private val permissions: List<String>) :
    User(name, age) {
    override fun display(): String = super.display() + " (admin): $permissions"
}

interface Reader {
    fun read(buffer: ByteArray): Int
}

enum class Status {
    ACTIVE,
    INACTIVE;

    fun label(): String = name.lowercase()
}

object Registry {
    private val entries = mutableMapOf<String, User>()

    fun register(user: User) {
        entries[user.name] = user
    }

    fun lookup(name: String): User? = entries[name]
}
