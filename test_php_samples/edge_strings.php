<?php

class Report
{
    public function render(string $name, int $count): string
    {
        $single = 'raw \n text';
        $double = "decoded \n text";
        $same_single = 'plain';
        $same_double = "plain";
        $interpolated = "Hello $name";
        $braced = "Count: {$count}";
        $complex = "Total: {$this->format($count)}";
        $literal = "cost: \$count";
        $heredoc = <<<EOT
    Report for $name
    EOT;
        $nowdoc = <<<'RAW'
    Raw $name text
    RAW;

        return implode(
            ' ',
            [$single, $double, $same_single, $same_double, $interpolated,
             $braced, $complex, $literal, $heredoc, $nowdoc],
        );
    }

    private function format(int $count): string
    {
        return number_format($count);
    }
}
