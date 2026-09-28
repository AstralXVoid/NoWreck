<?php

namespace App\Controller;

#[Route('/home')]
function home(): string
{
    return render('home');
}

#[Deprecated('use home()')]
#[Route('/about', methods: ['GET'])]
class PageController
{
    #[Inject(service: 'logger')]
    private Logger $logger;

    #[Route('/index')]
    #[Cache(maxage: 3600)]
    public function index(): string
    {
        return $this->layout(home());
    }

    public function layout(string $body): string
    {
        return wrap($body, $this->logger);
    }
}
