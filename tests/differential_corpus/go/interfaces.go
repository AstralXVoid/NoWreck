// Interfaces: interface types are INTERFACE symbols.
package shapes

type Shape interface {
	Area() float64
	Describe() string
}

type Named interface {
	Name() string
}

type Reader interface {
	Read(p []byte) (int, error)
}

type Closer interface {
	Close() error
}

type ReadCloser interface {
	Reader
	Closer
}

type Circle struct {
	Radius float64
}

type Square struct {
	Side float64
}

func (c Circle) Area() float64 {
	return math.Pi * c.Radius * c.Radius
}

func (c Circle) Describe() string {
	return "circle"
}

func (s Square) Area() float64 {
	return s.Side * s.Side
}

func (s Square) Describe() string {
	return "square"
}

func TotalArea(shapes []Shape) float64 {
	total := 0.0
	for _, s := range shapes {
		total += s.Area()
	}
	return total
}
