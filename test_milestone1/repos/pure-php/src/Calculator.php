<?php

namespace purephp;

class Calculator
{
    /** @var list<float> */
    private array $history = [];

    public function __construct(float $seed)
    {
        $this->history[] = $seed;
    }

    public function add(float $a, float $b): float
    {
        $result = $a + $b;
        $this->history[] = $result;
        return $result;
    }

    public function subtract(float $a, float $b): float
    {
        $result = $a - $b;
        $this->history[] = $result;
        return $result;
    }

    public function multiply(float $a, float $b): float
    {
        $result = $a * $b;
        $this->history[] = $result;
        return $result;
    }

    public function divide(float $a, float $b): float
    {
        $result = $a / $b;
        $this->history[] = $result;
        return $result;
    }

    public function display(): void
    {
        foreach ($this->history as $value) {
            echo $value, PHP_EOL;
        }
    }

    public static function computeAverage(array $values): float
    {
        return array_sum($values) / count($values);
    }
}
