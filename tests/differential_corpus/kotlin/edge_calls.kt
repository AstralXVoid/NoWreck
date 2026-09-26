// Dimension: every call shape the scanner claims, and the negatives that
// must stay negative — a call receiver (`f().bar()`), a callable reference
// (`::foo`), and a member dunder call.  A bare `__dunder__()` call and a
// constructor call (`Foo()`) are real calls in Kotlin: there is no `new`
// keyword, so the grammar sees an ordinary call expression (probe K5).

package com.example.calls

open class Base {
    open fun render(): String = "base"

    fun helper(): String = "helper"
}

class Renderer : Base() {
    fun plain(): Int {
        return compute()
    }

    fun member(value: Source): Int {
        return value.compute()
    }

    fun safe(value: Source?): Int? {
        return value?.compute()
    }

    fun asserted(value: Source?): Int {
        return value!!.compute()
    }

    fun onThis(): Int {
        return this.local()
    }

    override fun render(): String {
        val text = super.render()
        return text
    }

    fun chained(other: Holder): Int {
        return other.inner.value.compute()
    }

    fun indexed(items: List<Source>): Int {
        return items[0].compute()
    }

    fun assertedChain(other: Holder): Int {
        return other.source!!.compute()
    }

    fun reference(): () -> Int = ::local

    fun asArgument(): Int {
        return applyTo(::local)
    }

    fun withLambda(items: List<Int>): Int {
        return items.map { double(it) }.first()
    }

    fun literal(): Source {
        return Source()
    }

    fun fromCall(): Int {
        return literal().compute()
    }

    fun bare(): Int {
        return __bare__()
    }

    fun dunderMember(value: Source): Int {
        return value.__secret__()
    }

    private fun applyTo(func: () -> Int): Int = func()

    private fun double(value: Int): Int = value * 2

    private fun local(): Int = 3
}

class Source {
    fun compute(): Int = 1

    fun __secret__(): Int = 2
}

class Holder(val source: Source?, val inner: Source)
