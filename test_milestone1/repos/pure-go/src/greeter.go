package main

import "fmt"

func Greet(name string) string {
	greeting := FormatGreeting(name)
	return greeting
}

func FormatGreeting(name string) string {
	return fmt.Sprintf("Hello, %s!", name)
}

func Farewell(name string) string {
	return fmt.Sprintf("Goodbye, %s!", name)
}
