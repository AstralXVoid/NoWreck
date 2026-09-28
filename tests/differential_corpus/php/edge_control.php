<?php

function classify(int $n): string
{
    if ($n > 100) {
        $label = over($n);
    } elseif ($n > 0) {
        $label = under($n);
    } else {
        $label = zero();
    }

    foreach ([1, 2, 3] as $value) {
        $label .= append($value);
    }

    for ($i = 0; $i < 3; $i++) {
        $label = repeat($label, $i);
    }

    while (has_next()) {
        $label = step($label);
    }

    do {
        $label = once();
    } while (needs_more($label));

    try {
        $label = risky($label);
    } catch (Throwable $error) {
        $label = recover($error);
    } finally {
        finish();
    }

    switch (strlen($label)) {
        case 0:
            $label = empty_label();
            break;
        default:
            report($label);
    }

    return match (true) {
        $n === 0 => zero(),
        default => $label,
    };
}

if (!function_exists('conditional_helper')) {
    function conditional_helper(): string
    {
        return conditional();
    }
}

if (PHP_VERSION_ID >= 80000):
    function alternative_helper(): string
    {
        return alternative();
    }
endif;

while (pending()):
    report_cycle();
endwhile;
