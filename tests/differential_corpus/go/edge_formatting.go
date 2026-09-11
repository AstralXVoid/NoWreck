// Formatting variety: layout must never change symbol identity.
package fmtedge

func multilineCall(
	first int,
	second int, // trailing comment
) int {
	return first + second
}

type Wide struct {
	a int
	b int
}

func (w *Wide) method(
	a int,
	b int,
) int {
	return w.a - w.b + a - b
}

func    spaced   (x int) int { return x }

func compact() int { return 1 }

const (
	UnusedA = 1
	UnusedB = 2
)

func main() {
	result := multilineCall(
		1,
		2,
	)
	println(result)
}
