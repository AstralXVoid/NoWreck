// Edge: call shapes.
// - foo(), obj.method(), a.b.c() captured.
// - ns::func() / Class::static() excluded (parser boundary).
// - f().bar() (receiver is a call) excluded.

struct Widget {
    name: String,
}

impl Widget {
    fn new(name: String) -> Widget {
        Widget { name }
    }

    fn label(&self) -> String {
        self.name.to_uppercase()
    }

    fn describe(&self) -> String {
        format!("{}:{}", self.prefix(), self.label())
    }

    fn prefix(&self) -> &'static str {
        "W"
    }
}

fn format_widget(widget: &Widget) -> String {
    widget.describe()
}

fn chain(registry: &Registry) -> String {
    registry.get("a").put("b")
}

fn qualified(store: &std::collections::HashMap<String, i64>) -> Option<i64> {
    store.get("key").copied()
}

fn receivers(xs: &[i64]) -> Vec<i64> {
    xs.iter().map(|x| x * 2).filter(|x| *x > 1).collect()
}

fn turbofish() -> Vec<i64> {
    let xs = Vec::<i64>::new();
    xs.push(1);
    xs
}

struct Registry {
    entries: Vec<String>,
}

impl Registry {
    fn get(&self, key: &str) -> &Registry {
        let _ = key;
        self
    }

    fn put(&self, value: &str) -> String {
        value.to_string()
    }
}