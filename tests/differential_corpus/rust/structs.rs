// Structs and impl blocks: structs → class, impl fns → methods.

struct Point {
    x: f64,
    y: f64,
}

pub struct Account {
    owner: String,
    balance: f64,
}

struct User<'a> {
    name: &'a str,
    id: u64,
}

impl Point {
    fn new(x: f64, y: f64) -> Point {
        Point { x, y }
    }

    fn distance(&self, other: &Point) -> f64 {
        let dx = self.x - other.x;
        let dy = self.y - other.y;
        (dx * dx + dy * dy).sqrt()
    }

    fn origin() -> Point {
        Point { x: 0.0, y: 0.0 }
    }
}

impl Account {
    pub fn new(owner: String) -> Account {
        Account { owner, balance: 0.0 }
    }

    pub fn deposit(&mut self, amount: f64) {
        self.balance += amount;
    }

    pub fn withdraw(&mut self, amount: f64) -> bool {
        if amount > self.balance {
            return false;
        }
        self.balance -= amount;
        true
    }

    fn owner_name(&self) -> &str {
        &self.owner
    }
}

impl User<'_> {
    fn describe(&self) -> String {
        format!("{}#{}", self.name, self.id)
    }
}