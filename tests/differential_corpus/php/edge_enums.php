<?php

enum Status: string
{
    case Draft = 'draft';
    case Published = 'published';
    case Archived = 'archived';

    public function label(): string
    {
        return ucfirst($this->value);
    }

    public function is_editable(): bool
    {
        return match ($this) {
            Status::Draft, Status::Published => $this->check(),
            Status::Archived => false,
        };
    }

    private function check(): bool
    {
        return $this === Status::Draft;
    }
}

enum Priority: int implements HasRank
{
    case Low = 1;
    case High = 2;

    public function rank(): int
    {
        return $this->value;
    }
}

interface HasRank
{
    public function rank(): int;
}
