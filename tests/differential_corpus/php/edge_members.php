<?php

class Person
{
    public const GREETING = 'hello';

    public static int $instances = 0;

    private string $first;
    private string $last;

    protected ?string $nickname = null;

    public function __construct(string $first, string $last)
    {
        $this->first = $first;
        $this->last = $last;
        self::$instances++;
    }

    public string $full_name {
        get => $this->compose();
        set (string $value) {
            [$this->first, $this->last] = $this->split($value);
        }
    }

    private function compose(): string
    {
        return trim($this->first . ' ' . $this->last);
    }

    private function split(string $value): array
    {
        return preg_split('/\s+/', trim($value), 2);
    }
}
