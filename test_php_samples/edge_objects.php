<?php

interface Renderer
{
    public function render(string $view): string;
}

function make(array $config): Renderer
{
    $renderer = new class($config) implements Renderer {
        private array $config;

        public function __construct(array $config)
        {
            $this->config = $config;
        }

        public function render(string $view): string
        {
            return strtoupper($view);
        }
    };

    return $renderer;
}

function pipeline(object $source): string
{
    $chain = $source
        ->open()
        ->read()
        ->close();
    $maybe = $source?->read();

    return $chain . $maybe;
}
