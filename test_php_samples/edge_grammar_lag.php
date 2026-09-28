<?php

// PHP 8.4 asymmetric visibility in a *promoted* parameter is an ERROR in
// the pinned grammar (tree-sitter-php 0.24.1) — the parse stays partial
// and the scanner still reports what it can see.
class Config
{
    public function __construct(
        public private(set) string $name,
    ) {
    }

    public function name(): string
    {
        return $this->name;
    }
}
