// calls.cpp — the call-shape matrix.

void exercise(Request& request, Request* pointer, int index)
{
    request.send(payload());
    request->send(payload());
    Service::flush();
    ::boot();
    request.retry();
    queue[0].enqueue();
    (*pointer).notify();
    chain.next().last();
    direct();
    take(std::move(value));
    take(identity<int>(3));
    Request local(1);
    auto* made = new Request();
    (void)local;
    (void)made;
    assert(index >= 0);
}

struct Worker
{
    void run()
    {
        this->tick();
    }

    void tick() {}

    void reset()
    {
        // An explicit destructor call keeps its ``~`` name.
        this->~Worker();
    }

    template <typename T>
    T take()
    {
        return fetch();
    }
};

void template_site()
{
    Box<int> box;
    // A member-template call: the field node is a ``template_method``.
    box.put<int>(7);
}
