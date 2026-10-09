// edge_split.cpp — the implementation side of the header/impl split.

#include "edge_split.h"

Widget::Widget() : id_(0)
{
    register_self();
}

Widget::~Widget()
{
    release_self();
}

void Widget::draw()
{
    render_frame();
    resize(1, 2);
}

void Widget::resize(int width, int height)
{
    apply(width, height);
}

int total_widgets()
{
    return count_widgets();
}
