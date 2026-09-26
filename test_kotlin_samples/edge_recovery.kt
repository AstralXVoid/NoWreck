package samples.recovery

@Ann(1)
enum class SingleEntry {
    ONLY

    fun describe(): String {
        return recoveryWork()
    }
}

@Target(AnnotationTarget.CLASS)
annotation class AnnotatedAnnotation

@Deprecated("detached")
fun followed(): Int {
    return followedWork()
}

fun afterFollowed(): Int {
    return 2
}

enum class MultiEntry {
    ONE,
    TWO
}

@Ann(2)
object AnnotatedObject {
    fun work(): Int {
        return objectWork()
    }
}

class OneLine { fun oneLiner() {} }
