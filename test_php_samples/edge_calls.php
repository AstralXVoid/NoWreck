<?php

namespace App\Net;

class Client
{
    private array $items = [];

    public function send(object $transport): void
    {
        $transport->write('payload');
        helper();
        $this->retry();
        self::backup();
        static::backup();
        parent::boot();
        Client::backup();
        \App\Util\Logger::flush();
        \App\util\normalise('a');
        $transport?->maybe();
        $local = helper();
        $local->after();
        $transport->__construct();
        strlen(...);
        $transport->write(...);
        send_all(...$this->items);
        $transport->first()->last();
        $rows = $this->rows();
        $rows[0]->cell();
        (new Marker(1))->mark();
        new Marker(2);
        $dynamic = 'write';
        $transport->$dynamic();
        $transport->{'write'}();
        $obj->list();
        $callback = trim(...);
    }

    public function rows(): array
    {
        return $this->items;
    }

    protected function retry(): void
    {
    }

    public static function backup(): void
    {
    }
}

class Marker
{
    public function __construct(int $n)
    {
    }

    public function mark(): void
    {
    }
}
