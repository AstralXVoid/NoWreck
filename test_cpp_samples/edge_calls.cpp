// edge_calls.cpp — every call shape the scanner claims to support.

class Request
{
public:
    void send(int payload);
    void retry();
};

void exercise(Request& request, Request* pointer, int index)
{
    request.send(payload());
    request->send(payload());
    request.retry();
    Service::flush();
    ::boot();
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
