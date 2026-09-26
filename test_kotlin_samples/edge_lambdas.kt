package samples.lambdas

val topLevelLambda = { x: Int -> x + 1 }

val topLevelAnonymous = fun(x: Int): Int = x * 2

val plainValue = 41

class LambdaHolder {
    val field = { y: Int ->
        fieldWork()
        y * 2
    }

    val anonField = fun(): Int {
        return anonFieldWork()
    }

    val computed = compute()

    fun useLocals(): Int {
        val local = { n: Int -> localWork(n) }
        return local(1)
    }
}

fun trailingLambda(items: List<Int>): Int {
    var total = 0
    items.forEach { item ->
        total += item
    }
    items.map { it + 1 }
    return total
}
