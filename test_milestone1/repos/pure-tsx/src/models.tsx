// Data model components.

interface UserProps {
    username: string;
    email: string;
}

function UserCard({ username, email }: UserProps): JSX.Element {
    return (
        <div className="user">
            <span>{username}</span>
            <span>{email}</span>
        </div>
    );
}

const AdminCard = ({ username, email, role }: {
    username: string;
    email: string;
    role: string;
}): JSX.Element => {
    return (
        <div className="admin">
            <span>{username}</span>
            <span>{email}</span>
            <span>{role}</span>
        </div>
    );
};

class UserList extends React.Component {
    render(): JSX.Element {
        return (
            <ul>
                <UserCard username="ada" email="ada@example.com" />
                <AdminCard username="grace" email="grace@example.com" role="admin" />
            </ul>
        );
    }
}

// Type-level contracts (v0.8.0 material)
enum ViewMode {
    List,
    Grid,
    Detail,
}

type SortOrder = "asc" | "desc";
