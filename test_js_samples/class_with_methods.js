// Test case 3: Classes with methods

class UserService {
    constructor(name, email) {
        this.name = name;
        this.email = email;
    }

    getName() {
        return this.name;
    }

    getEmail() {
        return this.email;
    }

    validate() {
        if (!this.email.includes("@")) {
            throw new Error("Invalid email");
        }
        return true;
    }
}

class ApiClient {
    constructor(baseUrl) {
        this.baseUrl = baseUrl;
    }

    async fetch(path) {
        const response = await fetch(this.baseUrl + path);
        return response.json();
    }

    async get(path) {
        return this.fetch(path);
    }

    async post(path, data) {
        return this.fetch(path);
    }
}

// Edge case: empty class
class EmptyClass {
}

// Top-level function alongside classes
function helper() {
    return "helper";
}
