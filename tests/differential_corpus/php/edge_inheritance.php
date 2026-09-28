<?php

abstract class Animal
{
    public const KIND = 'animal';

    protected string $name;

    public function __construct(string $name)
    {
        $this->name = $name;
    }

    abstract public function sound(): string;

    public function describe(): string
    {
        return $this->name . ' says ' . $this->sound();
    }
}

class Dog extends Animal
{
    public function __construct(string $name)
    {
        parent::__construct($name);
    }

    public function sound(): string
    {
        return 'woof';
    }
}

final class Puppy extends Dog
{
    public function sound(): string
    {
        return strtolower(parent::sound());
    }
}

readonly final class Tag
{
    public function __construct(public string $code)
    {
    }
}
