// Calculator component.

class Calculator extends React.Component {
    add(a: number, b: number): number {
        return a + b;
    }

    subtract(a: number, b: number): number {
        return a - b;
    }

    multiply(a: number, b: number): number {
        const result = a * b;
        console.log("multiply(" + a + ", " + b + ") = " + result);
        return result;
    }

    divide(a: number, b: number): number {
        if (b === 0) {
            throw new Error("Cannot divide by zero");
        }
        return a / b;
    }

    render(): JSX.Element {
        return <div className="calculator">Calculator</div>;
    }
}

function computeAverage(values: number[]): number {
    const total = sum(values);
    const count = len(values);
    return total / count;
}
