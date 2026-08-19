pub struct User {
    pub name: String,
    pub age: u32,
}

impl User {
    pub fn display(&self) {
        println!("{}: {}", self.name, self.age);
    }

    pub fn to_dict(&self) -> String {
        format!("{{\"name\": \"{}\", \"age\": {}}}", self.name, self.age)
    }
}

pub struct AdminUser {
    pub user: User,
    pub permissions: Vec<String>,
}

impl AdminUser {
    pub fn display(&self) {
        println!("{} (admin): {:?}", self.user.name, self.permissions);
    }
}

// Type-level contracts (v0.8.0 material)
pub trait Display {
    fn fmt(&self) -> String;
}

pub enum Role {
    Admin,
    Member,
    Guest,
}

pub type UserStatus = String;
