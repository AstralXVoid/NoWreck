// Greeting components.

function Greeting({ name }: { name: string }): JSX.Element {
    const message = formatGreeting("Hello", name);
    return <div className="greeting">{message}</div>;
}

const formatGreeting = (template: string, name: string): string => {
    return template + ", " + name + "!";
};

const Farewell = ({ name }: { name: string }): JSX.Element => {
    const msg = "Goodbye, " + name + "!";
    return <div className="farewell">{msg}</div>;
};
