<?php

namespace purephp;

class User
{
    public function __construct(
        public string $name,
        public int $age,
    ) {
    }

    public function display(): string
    {
        return "{$this->name}: {$this->age}";
    }

    public function toDict(): string
    {
        return json_encode(['name' => $this->name, 'age' => $this->age]);
    }
}

class AdminUser extends User
{
    /** @var list<string> */
    private array $permissions;

    /** @param list<string> $permissions */
    public function __construct(string $name, int $age, array $permissions)
    {
        parent::__construct($name, $age);
        $this->permissions = $permissions;
    }

    public function display(): string
    {
        return parent::display() . ' (admin)';
    }
}

interface Reader
{
    public function read(int $length): string;
}

enum Status: string
{
    case Active = 'active';
    case Inactive = 'inactive';

    public function label(): string
    {
        return ucfirst($this->value);
    }
}

trait Registry
{
    /** @var array<string, User> */
    private array $entries = [];

    public function register(User $user): void
    {
        $this->entries[$user->name] = $user;
    }

    public function lookup(string $name): ?User
    {
        return $this->entries[$name] ?? null;
    }
}
