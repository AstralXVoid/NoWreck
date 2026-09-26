package samples.calls

open class BaseShapes {
    open fun onSuper(): String = "base"
}

class CallShapes : BaseShapes() {
    fun plain(): Int {
        return helper()
    }

    fun member(obj: Helper): Int {
        return obj.compute()
    }

    fun safeCall(value: Helper?): Int? {
        return value?.compute()
    }

    fun notNull(value: Helper?): Int {
        return value!!.compute()
    }

    fun onThis(): Int {
        return this.local()
    }

    override fun onSuper(): String {
        val text = super.onSuper()
        return text
    }

    fun chains(): Int {
        return a.b.c()
    }

    fun dynamic(): Int {
        return factory().result()
    }

    fun indexed(items: List<Helper>): Int {
        return items[0].compute()
    }

    fun chainedNotNull(obj: Container): Int {
        return obj.helper!!.compute()
    }

    fun reference(): () -> Int = ::local

    fun nestedLambda(items: List<Int>): Int {
        return items.map { inner(it) }.first()
    }

    fun outer(): Int {
        fun inner(): Int {
            return nestedCall()
        }
        return inner()
    }

    fun local(): Int {
        return 3
    }
}
