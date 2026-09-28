<?php

interface Renderer
{
    public function render(string $view): string;
}

function make_renderer(array $config): Renderer
{
    $renderer = new class($config) implements Renderer {
        private array $config;

        public function __construct(array $config)
        {
            $this->config = $config;
            bootstrap($config);
        }

        public function render(string $view): string
        {
            return $this->compile($view);
        }

        private function compile(string $view): string
        {
            return strtoupper($view);
        }
    };

    return $renderer;
}

function pipeline(object $source): string
{
    $chain = $source->open()->read()->close();
    $fallback = $source->read ?? 'none';
    $index = $source->read();
    $dynamic = 'read';
    $via_dynamic = $source->$dynamic();
    $nested_attr = $source->{'read'}();
    $direct = $source->read();

    return $chain . $fallback . $index . $via_dynamic . $nested_attr . $direct;
}
