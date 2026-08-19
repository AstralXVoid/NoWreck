package main

type Calculator struct {
	history []float64
}

func NewCalculator() *Calculator {
	return &Calculator{history: []float64{}}
}

func (c *Calculator) Add(a, b float64) float64 {
	result := a + b
	c.history = append(c.history, result)
	return result
}

func (c *Calculator) Subtract(a, b float64) float64 {
	result := a - b
	c.history = append(c.history, result)
	return result
}

func (c *Calculator) Multiply(a, b float64) float64 {
	result := a * b
	c.history = append(c.history, result)
	return result
}

func (c *Calculator) Divide(a, b float64) float64 {
	result := a / b
	c.history = append(c.history, result)
	return result
}

func (c *Calculator) Display() {
	for _, val := range c.history {
		println(val)
	}
}

func ComputeAverage(values []float64) float64 {
	sum := 0.0
	for _, v := range values {
		sum += v
	}
	return sum / float64(len(values))
}
