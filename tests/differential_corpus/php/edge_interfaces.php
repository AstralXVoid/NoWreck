<?php

interface Countable2
{
    public const DEFAULT_LIMIT = 10;

    public function count(): int;

    public function is_empty(): bool;
}

interface Sized extends Countable2
{
    public function size(): int;
}

class Bag implements Sized
{
    public function count(): int
    {
        return count($this->items());
    }

    public function is_empty(): bool
    {
        return $this->count() === 0;
    }

    public function size(): int
    {
        return $this->size_of($this->items());
    }

    private function size_of(array $items): int
    {
        return count($items);
    }

    private function items(): array
    {
        return [];
    }
}
