// Data models.

class User {
  constructor(username, email) {
    this.username = username;
    this.email = email;
  }

  display() {
    var info = "User(" + this.username + ", " + this.email + ")";
    console.log(info);
    return info;
  }

  toDict() {
    return {username: this.username, email: this.email};
  }
}

class AdminUser extends User {
  constructor(username, email, role) {
    super(username, email);
    this.role = role;
  }

  display() {
    var info = "Admin(" + this.username + ", " + this.email + ", role=" + this.role + ")";
    console.log(info);
    return info;
  }
}
