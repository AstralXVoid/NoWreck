<?php

trait HasUuid
{
    private ?string $uuid = null;

    public function uuid(): string
    {
        if ($this->uuid === null) {
            $this->uuid = $this->generate();
        }

        return $this->uuid;
    }

    private function generate(): string
    {
        return bin2hex(random_bytes(16));
    }
}

trait Timestamps
{
    public string $updated_at;

    public function touch(): void
    {
        $this->updated_at = date('c');
    }
}

class Record
{
    use HasUuid;
    use Timestamps;

    public function describe(): string
    {
        return $this->uuid() . ' @ ' . $this->updated_at;
    }
}
