<?php

namespace App;

interface Repository
{
    public function save(array $user): bool;
}

enum Status: string
{
    case Active = 'active';
    case Banned = 'banned';
}

class User
{
    public function __construct(
        public string $email,
        public Status $status = Status::Active,
    ) {
    }

    public function is_active(): bool
    {
        return $this->status === Status::Active;
    }
}

class InMemoryRepository implements Repository
{
    private array $rows = [];

    public function save(array $user): bool
    {
        $this->rows[] = $user;
        $this->notifyChanged(count($this->rows));

        return true;
    }

    private function notifyChanged(int $total): void
    {
        error_log('rows: ' . $total);
    }
}

function process(Repository $repo, array $rows): array
{
    $saved = [];
    foreach ($rows as $row) {
        if ($repo->save($row)) {
            $saved[] = $row;
        }
    }

    return $saved;
}

function main(): void
{
    $repo = new InMemoryRepository();
    $users = load_users();
    $saved = process($repo, $users);
    report(count($saved));
}

function load_users(): array
{
    return fetch_all();
}

function report(int $n): void
{
    error_log("saved $n");
}
