// Structs: struct types are classes; fields are shell content.
package models

type Point struct {
	X float64
	Y float64
}

type Account struct {
	Owner   string
	Balance float64
}

type User struct {
	Name string
	ID   uint64
}

type Coordinates struct {
	Lat, Lon float64
}

func NewPoint(x, y float64) Point {
	return Point{X: x, Y: y}
}

func Distance(a, b Point) float64 {
	dx := a.X - b.X
	dy := a.Y - b.Y
	return math.Sqrt(dx*dx + dy*dy)
}

type unexported struct {
	secret string
}
