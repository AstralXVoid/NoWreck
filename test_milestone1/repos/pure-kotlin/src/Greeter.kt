package purekotlin

fun greet(name: String): String = formatGreeting(name)

fun formatGreeting(name: String): String {
    val trimmed = name.trim()
    return "Hello, $trimmed!"
}

fun farewell(name: String): String = "Goodbye, $name!"
