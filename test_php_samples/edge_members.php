<?php

class Full
{
    public const LIMIT = 10;
    public static int $instances = 0;
    private string $first;
    protected ?string $nickname = null;

    public function __construct(
        private string $last,
        public string $code = 'x',
    ) {
        self::$instances++;
    }

    public string $full_name {
        get => $this->compose();
        set (string $value) {
            $this->assign($value);
        }
    }

    private function compose(): string
    {
        return $this->first . ' ' . $this->last;
    }

    private function assign(string $value): void
    {
        $this->first = $value;
    }
}

class Derived extends Full
{
    public function extra(): int
    {
        return 1;
    }
}
