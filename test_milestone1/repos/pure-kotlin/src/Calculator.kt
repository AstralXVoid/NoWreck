package purekotlin

class Calculator {
    private val history = mutableListOf<Double>()

    constructor(seed: Double) {
        history.add(seed)
    }

    fun add(a: Double, b: Double): Double {
        val result = a + b
        history.add(result)
        return result
    }

    fun subtract(a: Double, b: Double): Double {
        val result = a - b
        history.add(result)
        return result
    }

    fun multiply(a: Double, b: Double): Double {
        val result = a * b
        history.add(result)
        return result
    }

    fun divide(a: Double, b: Double): Double {
        val result = a / b
        history.add(result)
        return result
    }

    fun display() {
        history.forEach { value ->
            println(value)
        }
    }

    companion object {
        fun computeAverage(values: List<Double>): Double {
            var sum = 0.0
            values.forEach { value ->
                sum += value
            }
            return sum / values.size
        }
    }
}
