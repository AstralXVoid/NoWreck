// Greeting utilities.

function greet(name: string): string {
    const message = formatGreeting("Hello", name);
    console.log(message);
    return message;
}

const formatGreeting = (template: string, name: string): string => {
    return template + ", " + name + "!";
};

const farewell = (name: string): string => {
    const msg = "Goodbye, " + name + "!";
    console.log(msg);
    return msg;
};
