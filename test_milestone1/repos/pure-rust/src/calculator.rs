pub struct Calculator {
    history: Vec<f64>,
}

impl Calculator {
    pub fn new() -> Self {
        Calculator { history: Vec::new() }
    }

    pub fn add(&mut self, a: f64, b: f64) -> f64 {
        let result = a + b;
        self.history.push(result);
        result
    }

    pub fn subtract(&mut self, a: f64, b: f64) -> f64 {
        let result = a - b;
        self.history.push(result);
        result
    }

    pub fn multiply(&mut self, a: f64, b: f64) -> f64 {
        let result = a * b;
        self.history.push(result);
        result
    }

    pub fn divide(&mut self, a: f64, b: f64) -> f64 {
        let result = a / b;
        self.history.push(result);
        result
    }

    pub fn display(&self) {
        for val in &self.history {
            println!("{}", val);
        }
    }
}

pub fn compute_average(values: &[f64]) -> f64 {
    let sum: f64 = values.iter().sum();
    let len = values.len();
    sum / len as f64
}
