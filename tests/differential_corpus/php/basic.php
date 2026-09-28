<?php

declare(strict_types=1);

function slugify(string $text): string
{
    $trimmed = trim($text);
    $lower = strtolower($trimmed);
    $dashes = preg_replace('/\s+/', '-', $lower);

    return $dashes;
}

function describe(string $slug): string
{
    return 'Slug: ' . slugify($slug);
}

class Repository
{
    private array $rows = [];

    public function insert(array $row): void
    {
        $this->rows[] = $row;
    }

    public function count(): int
    {
        return count($this->rows);
    }

    public function first(): ?array
    {
        if ($this->rows === []) {
            return null;
        }

        return $this->rows[0];
    }
}
