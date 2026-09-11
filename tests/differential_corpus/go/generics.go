// Generics: generic functions, types, and receivers (Go 1.18+).
package generic

type Box[T any] struct {
	Value T
}

type Pair[K comparable, V any] struct {
	Key   K
	Value V
}

type HasID[T any] interface {
	ID() T
}

func NewBox[T any](value T) Box[T] {
	return Box[T]{Value: value}
}

func (b Box[T]) Get() T {
	return b.Value
}

func (b *Box[T]) Set(value T) {
	b.Value = value
}

func Find[T comparable](items []T, target T) int {
	for i, item := range items {
		if item == target {
			return i
		}
	}
	return -1
}

func Map[T, U any](items []T, fn func(T) U) []U {
	out := make([]U, 0, len(items))
	for _, item := range items {
		out = append(out, fn(item))
	}
	return out
}

type Number interface {
	~int | ~float64
}

func SumNumbers[T Number](items []T) T {
	var total T
	for _, item := range items {
		total += item
	}
	return total
}
