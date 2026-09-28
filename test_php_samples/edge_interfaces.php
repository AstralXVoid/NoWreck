<?php

interface Plain
{
    public function required(): string;
}

interface WithDefaults extends Plain
{
    public function provided(): int
    {
        return 10;
    }

    public function alsoProvided(): int;
}

class Impl implements WithDefaults
{
    public function required(): string
    {
        return 'x';
    }

    public function provided(): int
    {
        return 20;
    }
}
