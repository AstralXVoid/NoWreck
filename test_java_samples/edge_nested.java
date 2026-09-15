package samples.nested;

/** Nested, inner, local and anonymous class shapes. */
public class Outer {
    private int value;

    public void outerMethod() {
        helper();
    }

    private void helper() {
        value = 1;
    }

    public static class StaticNested {
        public void staticMethod() {
            innerHelper();
        }

        private void innerHelper() {
        }
    }

    public class Inner {
        public void innerMethod() {
            outerMethod();
        }
    }

    public void withLocalAndAnonymous() {
        class Local {
            void localMethod() {
                localHelper();
            }

            private void localHelper() {
            }
        }
        Runnable r = new Runnable() {
            @Override
            public void run() {
                anonymousHelper();
            }

            private void anonymousHelper() {
            }
        };
        r.run();
        new Local().localMethod();
    }
}
