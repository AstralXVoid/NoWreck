// Dimension: generics — type parameters, variance, bounds, star
// projections and generic extension functions.  None of it may become a
// symbol or a call, and a generic extension function is still a FUNCTION
// with no parent class (probe K4).

package com.example.generics

class Box<T>(val value: T) {
    fun get(): T = value

    fun <R> map(transform: (T) -> R): Box<R> {
        return Box(transform(value))
    }

    fun <R : Comparable<R>> maxBy(selector: (T) -> R): R? {
        return selector(value)
    }
}

class Cache<K : Comparable<K>, V : Any>(private val capacity: Int) {
    private val entries: MutableMap<K, V> = mutableMapOf()

    fun put(key: K, value: V): V? {
        evict()
        return entries.put(key, value)
    }

    fun get(key: K): V? = entries[key]

    private fun evict(): Unit {
        if (entries.size > capacity) {
            trim()
        }
    }

    private fun trim(): Unit {
        entries.clear()
    }
}

interface Producer<out T> {
    fun produce(): T
}

interface Consumer<in T> {
    fun consume(item: T)
}

fun <T> List<T>.secondOrNull(): T? = this.getOrNull(1)

fun <T : Comparable<T>> List<T>.sortedCopy(): List<T> = this.sorted()

fun <T> firstOrElse(items: List<T>, fallback: T): T {
    return if (items.isEmpty()) fallback else items.first()
}

fun wildcards(values: List<*>): Int {
    return values.size
}

fun nested(groups: Map<String, List<Int>>): Int {
    var total = 0
    for (entry in groups) {
        total += entry.value.size
    }
    return total
}
