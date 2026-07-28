// Edge case 8: Deeply nested functions and classes — only top-level should be captured
function topLevel() {
    function nested() {
        function deeplyNested() {
            return "deep";
        }
        return deeplyNested();
    }

    class InnerClass {
        method() {}
    }

    const innerArrow = () => {
        return "inner";
    };

    return nested();
}

class OuterClass {
    method() {
        function insideMethod() {
            return "inside";
        }
        return insideMethod();
    }
}

const outerArrow = () => {
    function insideArrow() {
        return "inside";
    }
    return insideArrow();
};
