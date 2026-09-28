<?php

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

    class BetaService
    {
        public function run(): string
        {
            return beta_helper();
        }
    }
}
