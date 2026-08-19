package main

// Basic Go constructs — all should be captured as symbols.

func greet(name string) string {
	return "Hello, " + name + "!"
}

func add(a, b int) int {
	return a + b
}

type User struct {
	Name string
	Age  int
}

func NewUser(name string, age int) *User {
	return &User{Name: name, Age: age}
}

func (u *User) Display() string {
	return u.Name
}

type Shape interface {
	Area() float64
}

type UserID int64
