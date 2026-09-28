<?php

class Compact { public function a(): int { return b(); } public function c(): int { return d(); } }

function wrapped(
    string $first,
    string $second = 'default',
): string {
    return join([$first, $second]);
}

final readonly class Config
{
    public const ARRAY_LIKE = ['a' => 1, 'b' => 2,];

    public function __construct(
        private string $name = 'config',
        private int $retries = 3,
    ) {
    }

    public function name(): string
    {
        return $this->name;
    }
}

// A comment holding fake code: function fake() { return phantom(); }
# Another fake: class Fake { public function ghost(): void { ghost_call(); } }

$trailing = trailing_call(
    'a',
    'b',
);
