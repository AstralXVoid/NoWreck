package main

import "fmt"

type User struct {
	Name string
	Age  int
}

func (u *User) Display() {
	fmt.Printf("%s: %d\n", u.Name, u.Age)
}

func (u *User) ToDict() string {
	return fmt.Sprintf("{\"name\": \"%s\", \"age\": %d}", u.Name, u.Age)
}

type AdminUser struct {
	User
	Permissions []string
}

func (a *AdminUser) Display() {
	fmt.Printf("%s (admin): %v\n", a.User.Name, a.Permissions)
}

// Type-level contracts
type Reader interface {
	Read(p []byte) (n int, err error)
}

type Status string
