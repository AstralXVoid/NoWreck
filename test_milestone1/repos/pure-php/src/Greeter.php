<?php

namespace purephp;

function greet(string $name): string
{
    return formatGreeting($name);
}

function formatGreeting(string $name): string
{
    $trimmed = trim($name);
    return "Hello, {$trimmed}!";
}

function farewell(string $name): string
{
    return "Goodbye, {$name}!";
}
