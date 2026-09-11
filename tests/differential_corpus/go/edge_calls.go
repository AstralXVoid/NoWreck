// Edge: call shapes.
// - foo(), obj.Method(), pkg.Func(), a.b.c() captured.
// - f().Bar() (receiver is a call) excluded.
package edge

type Widget struct {
	name string
}

func NewWidget(name string) *Widget {
	return &Widget{name: name}
}

func (w *Widget) Label() string {
	return strings.ToUpper(w.name)
}

func (w *Widget) Describe() string {
	return w.Prefix() + ":" + w.Label()
}

func (w *Widget) Prefix() string {
	return "W"
}

func FormatWidget(w *Widget) string {
	return w.Describe()
}

func Chain(registry *Registry) string {
	return registry.Get("a").Put("b")
}

func Qualified(m map[string]int) int {
	return m["key"]
}

func Receivers(xs []int) []int {
	out := []int{}
	for _, x := range xs {
		if x > 1 {
			out = append(out, x*2)
		}
	}
	return out
}

type Registry struct{}

func (r *Registry) Get(key string) *Registry {
	return r
}

func (r *Registry) Put(value string) string {
	return value
}

func BuiltinCalls(items []int) (int, int) {
	return len(items), cap(items)
}
