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

// The single-declaration ``extern "C"`` form: the declaration itself sits in
// the wrapper's ``body`` field (not a declaration list).
extern "C" int legacy_total();

// A reference-return declaration-only member at module scope.
Widget& active_widget();
