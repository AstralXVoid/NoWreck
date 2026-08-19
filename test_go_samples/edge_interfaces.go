package main

// Interface patterns — all should be captured.

type Reader interface {
	Read([]byte) (int, error)
}

type Writer interface {
	Write([]byte) (int, error)
}

// Composed interface
type ReadWriter interface {
	Reader
	Writer
}

// Buffer implements ReadWriter implicitly
type Buffer struct {
	data []byte
}

func (b *Buffer) Read(p []byte) (int, error) {
	n := copy(p, b.data)
	return n, nil
}

func (b *Buffer) Write(p []byte) (int, error) {
	b.data = append(b.data, p...)
	return len(p), nil
}

// Empty interface
type Any interface{}

// Interface with single method
type Stringer interface {
	String() string
}

// Multiple types implementing same interface
type Logger interface {
	Log(msg string)
}

type ConsoleLogger struct{}

func (c ConsoleLogger) Log(msg string) {
	println(msg)
}

type FileLogger struct {
	path string
}

func (f FileLogger) Log(msg string) {
	println(f.path + ": " + msg)
}
