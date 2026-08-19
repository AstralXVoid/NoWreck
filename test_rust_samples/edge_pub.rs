// Visibility modifiers — pub items should be captured, private items too.
// NoWreck captures ALL top-level symbols regardless of visibility.

pub fn public_function() -> i32 {
    42
}

fn private_function() -> i32 {
    0
}

pub(crate) fn crate_visible() -> bool {
    true
}

pub struct PublicStruct {
    pub field: i32,
}

struct PrivateStruct {
    value: String,
}

pub trait PublicTrait {
    fn method(&self);
}

trait PrivateTrait {
    fn private_method(&self);
}

pub enum PublicEnum {
    VariantA,
    VariantB,
}

enum PrivateEnum {
    Hidden,
}
