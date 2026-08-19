package main

// Negative tests — items that should NOT be captured as symbols.
// NoWreck captures only top-level declarations: functions, structs,
// interfaces, type aliases, and methods.
// Members (fields, methods on interfaces, constants) are NOT captured.

// Interface methods are NOT captured as symbols
type Repository interface {
    Find(id uint64) string
    Save(data string) bool
    Delete(id uint64)
}

// Struct fields are NOT captured as symbols
type Article struct {
    Title   string
    Content string
    Views   uint64
}

// Constants are NOT captured as symbols
const (
    MaxRetries = 3
    Timeout    = 30
)

// Variables are NOT captured as symbols
var globalConfig = Config{}

// Nested functions inside a function — NOT captured
func outer() {
    helper := func() int {
        return 42
    }
    _ = helper()
}

// Interface method implementations ARE captured (as methods),
// but the interface itself is separate.
func (a *Article) Summary() string {
    return a.Title
}

// Method on a non-struct type (type alias receiver) IS captured
type MyString string

func (s MyString) Upper() MyString {
    return MyString("UPPER")
}
