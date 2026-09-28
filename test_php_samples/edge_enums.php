<?php

enum Status: string
{
    case Draft = 'draft';
    case Live = 'live';

    public function label(): string
    {
        return ucfirst($this->value);
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

class Container
{
    public function useStatus(): string
    {
        return Status::Draft->label();
    }
}
