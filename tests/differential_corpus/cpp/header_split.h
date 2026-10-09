// header_split.h — declarations only (the header side of the split).

class Widget
{
public:
    Widget();
    ~Widget();

    void draw();
    void resize(int width, int height);

    virtual void update() = 0;

private:
    int id_;
};

int total_widgets();
