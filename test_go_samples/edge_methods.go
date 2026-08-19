package main

// Method patterns — value and pointer receivers.

type Counter struct {
	value int
}

// Value receiver
func (c Counter) Value() int {
	return c.value
}

// Pointer receiver
func (c *Counter) Increment() {
	c.value++
}

func (c *Counter) Reset() {
	c.value = 0
}

func (c *Counter) String() string {
	return "Counter"
}

// Multiple types with methods
type Calculator struct {
	result float64
}

func (calc *Calculator) Add(n float64) {
	calc.result += n
}

func (calc *Calculator) Subtract(n float64) {
	calc.result -= n
}

func (calc *Calculator) Result() float64 {
	return calc.result
}

func (calc *Calculator) Reset() {
	calc.result = 0
}

// Method on built-in type alias
type MyInt int

func (m MyInt) IsPositive() bool {
	return m > 0
}
