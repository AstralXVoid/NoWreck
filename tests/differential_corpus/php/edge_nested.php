<?php

class Pipeline
{
    public function run(array $items): array
    {
        $results = [];
        foreach ($items as $item) {
            $results[] = $this->step($item);
        }

        $clean = array_filter($results, function (int $value): bool {
            return $value > 0;
        });

        $tagged = array_map(function (int $value) use ($clean) {
            return $this->label($value, count($clean));
        }, $clean);

        if (!function_exists('local_helper')) {
            function local_helper(int $n): int
            {
                return local_adjust($n);
            }
        }

        return $this->finish($tagged);
    }

    private function step(int $item): int
    {
        return $item * 2;
    }

    private function label(int $value, int $total): string
    {
        return sprintf('%d/%d', $value, $total);
    }

    private function finish(array $values): array
    {
        return $values;
    }
}
