// TSX edge cases — IIFE skip, types-only negatives, calls in JSX-in-body
interface User {
    id: number;
    name: string;
}

type Status = "active" | "inactive";

enum Color {
    Red,
    Green,
}

const config = (() => {
    return { theme: "dark" };
})();

function useUser(id: number): User {
    const user = fetchUser(id);
    return { id, name: user.name };
}

function Dashboard(): JSX.Element {
    const user = useUser(1);
    return (
        <div>
            <span>{user.name}</span>
        </div>
    );
}

const workingArrow = (x: number): number => {
    return x * 2;
};
