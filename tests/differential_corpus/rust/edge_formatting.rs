// Formatting variety: layout must never change symbol identity.

fn multiline_call(
    first: i64,
    second: i64, // trailing comment
) -> i64 {
    first + second
}

struct Wide {
    a: i64,
    b: i64,
}

impl Wide {
    fn method(
        &self,
        a: i64,
        b: i64,
    ) -> i64 {
        self.a - self.b + a - b
    }
}

fn    spaced    ( x : i64 ) -> i64 { x }

fn compact(){1}

const    _UNUSED   : i64 = 3;

type   weird   =   String;

fn main() {
    let result = multiline_call(
        1,
        2,
    );
    println!("{result}");
}