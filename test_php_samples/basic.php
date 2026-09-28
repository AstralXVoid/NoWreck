<?php

interface Greeter
{
    public function greet(string $name): string;
}

class Person implements Greeter
{
    private string $name;

    public function __construct(string $name)
    {
        $this->name = $name;
    }

    public function greet(string $name): string
    {
        return 'Hello, ' . $name;
    }
}

enum Color
{
    case Red;
    case Blue;
}

trait Loggable
{
    public function log(string $message): void
    {
        error_log($message);
    }
}

function topLevel(string $text): string
{
    return strtoupper($text);
}

$double = function (int $n): int
{
    return $n * 2;
};
