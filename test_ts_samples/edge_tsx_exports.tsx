// TSX export shapes — named defaults, anonymous defaults, generics, interfaces
export default function App(): JSX.Element {
    return <div>app</div>;
}

export function Header({ text }: { text: string }): JSX.Element {
    return <h1>{text}</h1>;
}

export const Footer = (): JSX.Element => {
    return <footer>footer</footer>;
};

interface ListProps {
    items: string[];
}

function List<T>({ items }: ListProps): JSX.Element {
    return <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul>;
}

export class AdminPanel extends React.Component {
    render(): JSX.Element {
        return <List items={["a", "b"]} />;
    }
}
