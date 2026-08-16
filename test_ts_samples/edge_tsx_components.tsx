// Core positive patterns for TSX scanning — component shapes
function Greeting({ name }: { name: string }): JSX.Element {
    return <div>Hello, {name}!</div>;
}

const Card = ({ title }: { title: string }) => {
    return (
        <div className="card">
            <h2>{title}</h2>
        </div>
    );
};

class Profile extends React.Component {
    render(): JSX.Element {
        return <Greeting name="Ada" />;
    }
}

function Page(): JSX.Element {
    return (
        <>
            <Greeting name="Grace" />
            <Card title="Notes" />
        </>
    );
}
