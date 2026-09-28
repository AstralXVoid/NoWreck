<?php

$double = function (int $n): int
{
    return $n * 2;
};

$triple = fn (int $n): int => $n * 3;

$static = static function (string $text): string
{
    return strtoupper(trim($text));
};

$counter = function () use (&$total) {
    $total = $total + 1;

    return $total;
};

function run(array $items): array
{
    $mapped = array_map(function (int $item): int {
        return normalise($item);
    }, $items);

    $arrow = fn (int $item): int => double_up($item);

    return array_filter($mapped, $arrow);
}
