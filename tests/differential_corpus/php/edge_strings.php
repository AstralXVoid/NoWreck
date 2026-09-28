<?php

function render_report(string $name, int $count): string
{
    $single = 'raw \n text';
    $double = "decoded \n text";
    $same_single = 'plain';
    $same_double = "plain";
    $interpolated = "Hello $name";
    $braced = "Count: {$count}";
    $with_call = 'Total: ' . number_format($count);
    $complex = "Total: {$this->format($count)}";
    $literal_dollar = "cost: \$count";
    $heredoc = <<<EOT
    Report for $name
    EOT;
    $nowdoc = <<<'RAW'
    Raw $name text
    RAW;

    return implode(' ', [
        $single,
        $double,
        $same_single,
        $same_double,
        $interpolated,
        $braced,
        $with_call,
        $complex,
        $literal_dollar,
        $heredoc,
        $nowdoc,
    ]);
}
