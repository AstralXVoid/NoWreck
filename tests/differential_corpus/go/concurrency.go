// Concurrency: goroutines, channels, sync primitives.
package worker

type Pool struct {
	jobs    chan int
	results chan int
}

func NewPool(size int) *Pool {
	return &Pool{
		jobs:    make(chan int, size),
		results: make(chan int, size),
	}
}

func (p *Pool) Start(workers int) {
	for i := 0; i < workers; i++ {
		go p.worker()
	}
}

func (p *Pool) worker() {
	for job := range p.jobs {
		p.results <- job * 2
	}
}

func (p *Pool) Submit(job int) {
	p.jobs <- job
}

func (p *Pool) Collect() int {
	return <-p.results
}

func (p *Pool) Close() {
	close(p.jobs)
}

func RunConcurrent(items []int, workers int) []int {
	pool := NewPool(workers)
	pool.Start(workers)
	for _, item := range items {
		pool.Submit(item)
	}
	pool.Close()
	out := make([]int, 0, len(items))
	for range items {
		out = append(out, pool.Collect())
	}
	return out
}

func WithMutex() {
	var mu sync.Mutex
	mu.Lock()
	defer mu.Unlock()
}
