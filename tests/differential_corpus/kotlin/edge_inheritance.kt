// Dimension: inheritance — open/abstract/sealed hierarchies, `override`,
// `super` calls, interface delegation with `by`, and abstract members.
// A supertype constructor is a delegation, not a call; a `super.foo()` and
// a delegated interface call are calls.

package com.example.inheritance

interface Logger {
    fun log(message: String)
}

interface Tracker {
    fun track(event: String): Int
}

abstract class Entity(val id: String) {
    abstract fun describe(): String

    open fun render(): String = "entity:$id"

    fun identity(): String {
        return describe() + render()
    }
}

open class User(id: String, val name: String) : Entity(id) {
    override fun describe(): String = "user:$name"

    override fun render(): String {
        return super.render() + "!" + describe()
    }
}

class Admin(id: String, name: String, private val level: Int) : User(id, name) {
    override fun describe(): String {
        val base = super.describe()
        return base + " admin:$level"
    }

    fun escalate(): String {
        return describe().uppercase()
    }
}

sealed class Shape {
    abstract fun area(): Double

    class Circle(val radius: Double) : Shape() {
        override fun area(): Double = radius * radius
    }

    class Square(val side: Double) : Shape() {
        override fun area(): Double = side * side
    }
}

class Service(id: String) : Entity(id), Logger, Tracker by InMemoryTracker() {
    private var count = 0

    override fun describe(): String = "service:$id"

    override fun log(message: String) {
        count += 1
        record(message)
    }

    override fun track(event: String): Int = count

    private fun record(message: String): Unit {
        println(message)
    }
}

class InMemoryTracker : Tracker {
    private val events: MutableList<String> = mutableListOf()

    override fun track(event: String): Int {
        events.add(event)
        return events.size
    }
}

class PlainTracker : Tracker {
    override fun track(event: String): Int = 0
}
