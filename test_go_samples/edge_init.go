package main

// init and package-level patterns.

func init() {
	// init function — should be captured
	println("initialized")
}

var globalConfig = DefaultConfig()

// Closure-returning function
func makeCounter() func() int {
	count := 0
	return func() int {
		count++
		return count
	}
}

// Function returning error
func validateInput(input string) error {
	if input == "" {
		return nil
	}
	return nil
}

// Multiple init functions (Go allows this)
func init() {
	println("second init")
}

// Goroutine-launching function
func runAsync(fn func()) {
	go fn()
}

// Channel-returning function
func createChannel() chan int {
	ch := make(chan int)
	return ch
}
