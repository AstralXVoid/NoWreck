// Edge: code-like text inside strings and comments must be ignored.
// func fakeFunction() int { return 1 }
// Example: fmt.Println("not a real call")

package edge

func realFunction() string {
	doc := `
		func documentedExample() int {
			"shown in docs, not indexed"
		}
	`
	sample := `use sum([3, 1]) and filter(x > 0)`
	return doc + sample
}

func rawContainsCode() string {
	return `func alsoFake() { println("nested") }`
}

func interpretedAndRune() (string, rune) {
	s := "print('nested')"
	r := 'x'
	return s, r
}

func backtickWithBacktick() string {
	inner := `tick: ` + "`" + ` here`
	return inner
}

// A ``//`` inside a string must not start a comment that eats the call
// after it on the same line.
func commentMarkerInString() string {
	url := "https://example.com/a/b"; n := post(url)
	return n
}
