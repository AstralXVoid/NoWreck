package main

// Exported (capitalized) vs unexported names.
// NoWreck captures ALL top-level symbols regardless of export status.

// Exported functions
func ExportedFunc() string {
	return "exported"
}

// Unexported functions
func unexportedFunc() string {
	return "unexported"
}

// Exported struct
type ExportedStruct struct {
	Field string
}

// Unexported struct
type unexportedStruct struct {
	field string
}

// Exported interface
type ExportedInterface interface {
	Method()
}

// Unexported interface
type unexportedInterface interface {
	method()
}

// Exported enum (via const block)
type Status int

const (
	StatusActive   Status = iota
	StatusInactive Status = 2
)

// Unexported type
type internalID int64
