// Methods: value and pointer receivers.
package store

type Account struct {
	owner   string
	balance float64
}

func NewAccount(owner string) *Account {
	return &Account{owner: owner, balance: 0}
}

func (a *Account) Deposit(amount float64) {
	a.balance += amount
}

func (a *Account) Withdraw(amount float64) bool {
	if amount > a.balance {
		return false
	}
	a.balance -= amount
	return true
}

func (a Account) Balance() float64 {
	return a.balance
}

func (a *Account) Owner() string {
	return a.owner
}

type Metrics struct {
	count int
}

func (m *Metrics) Inc() {
	m.count++
}

func (m Metrics) Value() int {
	return m.count
}

func Register(m *Metrics) {
	m.Inc()
}
