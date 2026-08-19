package main

// Generic patterns (Go 1.18+) — all should be captured.

func First[T any](items []T) T {
	return items[0]
}

func Contains[T comparable](items []T, target T) bool {
	for _, item := range items {
		if item == target {
			return true
		}
	}
	return false
}

type Number interface {
	~int | ~int32 | ~int64 | ~float32 | ~float64
}

func Sum[T Number](items []T) T {
	var total T
	for _, item := range items {
		total += item
	}
	return total
}

type Pair[A any, B any] struct {
	First  A
	Second B
}

func NewPair[A any, B any](a A, b B) Pair[A, B] {
	return Pair[A, B]{First: a, Second: b}
}

func Map[T any, R any](items []T, f func(T) R) []R {
	result := make([]R, len(items))
	for i, item := range items {
		result[i] = f(item)
	}
	return result
}

type Stack[T any] struct {
	items []T
}

func (s *Stack[T]) Push(item T) {
	s.items = append(s.items, item)
}

func (s *Stack[T]) Pop() T {
	item := s.items[len(s.items)-1]
	s.items = s.items[:len(s.items)-1]
	return item
}
