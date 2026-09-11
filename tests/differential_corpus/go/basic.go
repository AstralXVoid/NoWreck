// Package util provides basic helpers.
package util

const Prefix = "app"

func Greet(name string, excited bool) string {
	message := Prefix + ": " + name
	if excited {
		return strings.ToUpper(message)
	}
	return message
}

func Sum(values []int) int {
	total := 0
	for _, value := range values {
		total += value
	}
	return total
}

func internalHelper(value int) int {
	return value * 2
}

func ComputeTotal(values []int) int {
	total := 0
	for _, value := range values {
		total += internalHelper(value)
	}
	return total
}

func main() {
	total := ComputeTotal([]int{1, 2, 3})
	println(total)
}

var result = Sum([]int{1, 2, 3})
