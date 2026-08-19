package main

// Struct patterns — embedding, anonymous fields.

type Base struct {
	ID   int
	Name string
}

type Extended struct {
	Base
	Extra string
}

func (e Extended) FullName() string {
	return e.Name + " " + e.Extra
}

// Nested structs
type Address struct {
	Street string
	City   string
}

type Person struct {
	Name    string
	Address Address
}

func (p Person) Location() string {
	return p.Address.City
}

// Anonymous struct field
type Config struct {
	Timeout int
	Retries int
}

func DefaultConfig() Config {
	return Config{Timeout: 30, Retries: 3}
}

// Struct with function field
type Handler struct {
	Handle func(string) error
}

func (h Handler) Process(input string) error {
	return h.Handle(input)
}
