package samples.calls;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

class Base {
    void helper() {
    }
}

/** Every call shape the scanner captures, and the ones it must not. */
public class CallShapes extends Base {
    private final List<String> items = new ArrayList<>();
    private final int[] data = new int[3];

    void plainCall() {
        helper();
    }

    void memberCall() {
        this.helper();
    }

    @Override
    void helper() {
        super.helper();
    }

    void qualifiedCall() {
        CallShapes.staticHelper();
    }

    void indexReceiver() {
        data[0] = 1;
        items.get(0).trim();
    }

    void dynamicReceiver() {
        factory().helper();
    }

    void excludedDunder() {
        this.__magic__();
    }

    void bareDunder() {
        __plain__();
    }

    void constructors() {
        CallShapes other = new CallShapes();
        Supplier<CallShapes> maker = CallShapes::new;
        other.plainCall();
    }

    void references() {
        Supplier<String> name = this::toString;
    }

    void lambda() {
        items.forEach(item -> consume(item));
    }

    void nestedLambda() {
        items.forEach(item -> items.forEach(inner -> consume(inner)));
    }

    private CallShapes factory() {
        return new CallShapes();
    }

    private static void staticHelper() {
    }

    private void __magic__() {
    }

    private static void __plain__() {
    }

    private void consume(String value) {
        value.trim();
    }
}
