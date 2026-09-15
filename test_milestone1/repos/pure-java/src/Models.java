package purejava;

import java.util.List;

public class User {
    private final String name;
    private final int age;

    public User(String name, int age) {
        this.name = name;
        this.age = age;
    }

    public String display() {
        return name + ": " + age;
    }

    public String toDict() {
        return "{\"name\": \"" + name + "\", \"age\": " + age + "}";
    }
}

class AdminUser extends User {
    private final List<String> permissions;

    AdminUser(String name, int age, List<String> permissions) {
        super(name, age);
        this.permissions = permissions;
    }

    @Override
    public String display() {
        return super.display() + " (admin): " + permissions;
    }
}

interface Reader {
    int read(byte[] buffer);
}

enum Status {
    ACTIVE, INACTIVE
}
