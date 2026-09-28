<?php

namespace App\Service;

use App\Repository\UserRepository;
use App\Support\Formatter;

class UserService
{
    private UserRepository $repository;

    public function __construct(UserRepository $repository)
    {
        $this->repository = $repository;
    }

    public function register(string $email, string $name): array
    {
        $normalised = Formatter::normalise_email($email);

        if ($this->repository->exists($normalised)) {
            throw new \RuntimeException(sprintf('Duplicate: %s', $normalised));
        }

        $user = [
            'email' => $normalised,
            'name' => trim($name),
            'slug' => Formatter::slug($name),
        ];

        $saved = $this->repository->save($user);

        return [
            'id' => $saved->id,
            'summary' => sprintf('%s <%s>', $saved->name, $saved->email),
        ];
    }

    public function summary(int $id): string
    {
        $user = $this->repository->find($id);

        if ($user === null) {
            return (string) $id;
        }

        $greeting = "Hello {$user->name}";

        return $greeting . ' — ' . $this->describe($user);
    }

    private function describe(object $user): string
    {
        $roles = $user->roles ?? [];

        return implode(', ', $roles);
    }
}
