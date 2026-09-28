<?php

declare(strict_types=1);

namespace App\Flat;

use App\Flat\Support\Formatter;

function flat_helper(): string
{
    return Formatter::format('x');
}

class FlatService
{
    public function run(): string
    {
        return flat_helper();
    }
}

namespace App\Alpha {
    function alpha_helper(): string
    {
        return alpha_inner();
    }

    class AlphaService
    {
        public function run(): string
        {
            return alpha_helper();
        }
    }
}

namespace App\Beta {
    function beta_helper(): string
    {
        return beta_inner();
    }
}
