// TSX handler shapes — inline arrows, identifier handlers, member calls
function Button({ label, onClick }: { label: string; onClick: () => void }) {
    const handleClick = () => {
        trackEvent("button");
    };
    return <button onClick={onClick}>{label}</button>;
}

function Form(): JSX.Element {
    const submit = () => {
        sendForm();
    };
    return (
        <form onSubmit={submit}>
            <button onClick={() => submit()}>Go</button>
        </form>
    );
}

class Toggle extends React.Component {
    toggle(): void {
        flipState();
    }
    render(): JSX.Element {
        return <button onClick={() => this.toggle()}>Toggle</button>;
    }
}
