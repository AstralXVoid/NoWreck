package samples.negatives

class Negatives {
    fun dunderMember(obj: Helper) {
        obj.__secret__()
    }

    fun bareDunder() {
        __bare__()
    }

    fun constructorCall() {
        val helper = Helper()
        helper.use()
    }

    fun tagged(name: String) {
        @Suppress("UNUSED")
        val value = name.length
    }

    fun infix(a: Int) {
        val pair = a to a
    }
}

fun declarationsOnly() {
    val notACall = 1
}

class __DunderClass {
    fun regular() {
        return
    }
}
