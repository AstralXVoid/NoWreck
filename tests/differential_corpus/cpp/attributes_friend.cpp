// attributes_friend.cpp — attributes, friends, defaults and specifiers.

[[nodiscard]] int compute(int value);

class Engine
{
public:
    Engine();
    Engine(const Engine& other) = delete;
    Engine& operator=(const Engine& other) = default;

    [[nodiscard]] int gauge() const;

    virtual void start() = 0;
    virtual void stop() noexcept;

    friend void assist(Engine& engine);

private:
    static const int kLimit = 8;
    int level_;
};

void Engine::stop() noexcept
{
    wind_down();
}

void assist(Engine& engine)
{
    engine.reset();
}
