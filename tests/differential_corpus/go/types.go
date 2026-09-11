// Type aliases and defined types: every non-struct/interface form maps
// to TYPE_ALIAS (parser boundary).
package types

type ID = string

type Callback = func(int) int

type UserID uint64

type Temperature float64

type IntList []int

type Lookup map[string]int

type Pair struct {
	Left  int
	Right int
}

type Handler interface {
	Handle(event string) error
}

func UseAlias(id ID) ID {
	return id
}

func UseCallback(cb Callback) int {
	return cb(1)
}

type (
	Alpha struct{ V int }
	Beta  = string
)

var (
	Version = "1.0"
	Build   = "dev"
)
