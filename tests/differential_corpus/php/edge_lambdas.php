<?php

$double = function (int $n): int {
    return $n * 2;
};

$triple = fn (int $n): int => $n * 3;

$static = static function (string $text): string {
    return strtoupper(trim($text));
};

$counter = function () use (&$total) {
    $total = $total + 1;

    return $total;
};

function transform(array $items): array
{
    $mapped = array_map(function (int $item): int {
        return normalise($item);
    }, $items);

    $arrow = fn (int $item): int => double_up($item);

    $nested = function (int $item) use ($arrow) {
        $inner = fn (int $x): int => $arrow($x);

        return $inner($item);
    };

    return array_filter($mapped, $arrow);
}
