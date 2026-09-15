// Dimension: a realistic service class — the shapes a real repo mixes:
// nested DTOs, generics, streams, a private helper chain, an immutable
// record, a nested enum and a package-private constructor.

package com.example.realworld;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;

public final class UserService {
    private static final int PAGE_SIZE = 25;

    private final UserRepository repository;
    private final Clock clock;
    private final List<String> auditTrail = new ArrayList<>();

    UserService(UserRepository repository, Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }

    public Optional<User> find(String id) {
        recordAudit("find");
        return repository.lookup(id);
    }

    public List<User> activeUsers() {
        List<User> users = repository.all();
        List<User> active = new ArrayList<>();
        for (User user : users) {
            if (isActive(user)) {
                active.add(user);
            }
        }
        active.sort(Comparator.comparing(User::name));
        return active.subList(0, Math.min(PAGE_SIZE, active.size()));
    }

    public User create(String name, String email) {
        validate(name, email);
        User user = new User(name, email, clock.now());
        repository.save(user);
        recordAudit("create");
        return user;
    }

    private boolean isActive(User user) {
        return !user.disabled();
    }

    private void validate(String name, String email) {
        requireNonEmpty(name, "name");
        requireNonEmpty(email, "email");
    }

    private void requireNonEmpty(String value, String field) {
        if (value.isEmpty()) {
            throw new IllegalArgumentException(field + " required");
        }
    }

    private void recordAudit(String action) {
        auditTrail.add(stamp(action));
    }

    private String stamp(String action) {
        return action + "@" + clock.now();
    }

    public record User(String name, String email, long createdAt) {
        public User {
            check(name, email);
        }

        boolean disabled() {
            return createdAt == 0;
        }

        static void check(String name, String email) {
            name.trim();
            email.trim();
        }
    }

    public enum Status {
        ACTIVE {
            @Override
            boolean visible() {
                return true;
            }
        },
        DISABLED {
            @Override
            boolean visible() {
                return false;
            }
        };

        abstract boolean visible();
    }
}

interface UserRepository {
    Optional<UserService.User> lookup(String id);

    List<UserService.User> all();

    void save(UserService.User user);
}

interface Clock {
    long now();
}
