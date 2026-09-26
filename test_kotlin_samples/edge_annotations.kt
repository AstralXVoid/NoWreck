package samples.annotations

@Deprecated("old")
fun annotatedLast() {
    return
}

@Suppress("UNUSED_PARAMETER")
class AnnotatedClass(val value: Int) {
    @JvmField
    val field = 1

    @Deprecated("gone")
    fun method() {
        memberWork()
    }

    @get:JvmName("renamed")
    val aliased = 2
}

class MultiAnnotated {
    @Deprecated("a")
    @Suppress("UNUSED")
    fun multi() {
        multiWork()
    }
}

@Target(AnnotationTarget.CLASS)
@Retention(AnnotationRetention.RUNTIME)
annotation class Marker

@Suppress("UNUSED")
object AnnotatedObject {
    fun inside(): Int {
        return objectWork()
    }
}
