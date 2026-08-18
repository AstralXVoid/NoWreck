// Data models.

class User {
    constructor(username: string, email: string) {
        this.username = username;
        this.email = email;
    }

    display(): string {
        const info = "User(" + this.username + ", " + this.email + ")";
        console.log(info);
        return info;
    }

    toDict(): object {
        return {username: this.username, email: this.email};
    }
}

class AdminUser extends User {
    constructor(username: string, email: string, role: string) {
        super(username, email);
        this.role = role;
    }

    display(): string {
        const info =
            "Admin(" + this.username + ", " + this.email + ", role=" + this.role + ")";
        console.log(info);
        return info;
    }
}

// Type-level contracts (v0.8.0 material)
interface UserProfile {
    username: string;
    email: string;
}

enum Role {
    Admin,
    Member,
    Guest,
}

type UserStatus = "active" | "suspended" | "deleted";
