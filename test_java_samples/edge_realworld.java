/*
 * A realistic multi-class module: comments, generics, exceptions,
 * concurrency-friendly collections, nested and inner types.
 */

package samples.realworld;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;

/** In-memory user store with a small service layer. */
public final class UserService {

    private final ConcurrentHashMap<Long, User> users = new ConcurrentHashMap<>();
    private long nextId = 1L;

    /** Create and store a user. */
    public User create(String name, String email) {
        validate(name, email);
        long id = nextId++;
        User user = new User(id, name, email);
        users.put(id, user);
        audit("created", id);
        return user;
    }

    public List<User> all() {
        List<User> out = new ArrayList<>(users.values());
        out.sort((a, b) -> a.name().compareTo(b.name()));
        return out;
    }

    public User find(long id) {
        User user = users.get(id);
        if (user == null) {
            throw new NotFoundException("no user " + id);
        }
        return user;
    }

    // helper methods

    private void validate(String name, String email) {
        if (name == null || name.isEmpty()) {
            throw new IllegalArgumentException("name required");
        }
        if (email == null || !email.contains("@")) {
            throw new IllegalArgumentException("bad email");
        }
    }

    private void audit(String action, long id) {
        Logger.log(action + "#" + id);
    }

    /** A stored user. */
    public record User(long id, String name, String email) {
        public String display() {
            return name + " <" + email + ">";
        }
    }

    public static class NotFoundException extends RuntimeException {
        public NotFoundException(String message) {
            super(message);
        }
    }

    static final class Logger {
        static void log(String message) {
            System.out.println(message);
        }
    }

    private static final class Cache<K, V> {
        private final ConcurrentHashMap<K, V> store = new ConcurrentHashMap<>();

        void put(K key, V value) {
            store.put(key, value);
        }

        V get(K key) {
            return store.get(key);
        }
    }
}
