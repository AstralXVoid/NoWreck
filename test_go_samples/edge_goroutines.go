package main

// Goroutine and channel patterns — concurrency constructs are structural
// detail. NoWreck captures the enclosing function/type, not the goroutine
// or channel operations themselves.

// Function that launches a goroutine
func runAsync() {
    go func() {
        // anonymous goroutine — not a symbol
        _ = 42
    }()
}

// Function with channel creation and usage
func createChannel() chan int {
    ch := make(chan int, 10)
    go func() {
        for i := 0; i < 10; i++ {
            ch <- i
        }
        close(ch)
    }()
    return ch
}

// Function using select
func selectOnChannels(ch1, ch2 chan int) int {
    select {
    case v := <-ch1:
        return v
    case v := <-ch2:
        return v
    default:
        return -1
    }
}

// Struct with channel field
type Pipeline struct {
    input  chan string
    output chan string
    done   chan struct{}
}

// Method on pipeline struct
func (p *Pipeline) Run() {
    for msg := range p.input {
        p.output <- msg
    }
    close(p.done)
}

// Interface satisfied by pipeline
type Processor interface {
    Run()
}

// Type alias for channel
type MessageChan = chan string
