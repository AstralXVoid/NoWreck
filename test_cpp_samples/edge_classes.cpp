// edge_classes.cpp — class, struct and union shapes plus member specifiers.

class Engine
{
public:
    Engine();
    ~Engine();

    Engine(const Engine& other) = delete;
    Engine& operator=(const Engine& other) = default;

    void start();
    void stop() noexcept;

    [[nodiscard]] int gauge() const
    {
        return level_;
    }

    static int instances();

protected:
    void reset();

private:
    int level_ = 0;
};

struct Coord
{
    double x;
    double y;

    double length() const
    {
        return compute(x, y);
    }
};

union Value
{
    int as_int;
    double as_double;
};

void drive()
{
    Engine engine;
    engine.start();
    engine.stop();
    engine.gauge();
    engine.reset();
    (void)engine;
}
