package main

import "fmt"

// Multiple methods on same type
func (u *User) UpdateName(name string) {
	u.Name = name
}

func (u *User) Validate() bool {
	return u.Name != ""
}

// Interface with multiple methods
type ReadWriter interface {
	Read([]byte) (int, error)
	Write([]byte) (int, error)
}

// Struct implementing interface
type Buffer struct {
	data []byte
}

func (b *Buffer) Read(p []byte) (int, error) {
	copy(p, b.data)
	return len(b.data), nil
}

func (b *Buffer) Write(p []byte) (int, error) {
	b.data = append(b.data, p...)
	return len(p), nil
}

// Type aliases
type Callback func(string) error
type StringMap map[string]string

// Function with closure
func makeCounter() func() int {
	count := 0
	return func() int {
		count++
		return count
	}
}

// Function calling another
func processUser(u *User) string {
	if u.Validate() {
		return u.Display()
	}
	return "invalid"
}

func init() {
	fmt.Println("init")
}
