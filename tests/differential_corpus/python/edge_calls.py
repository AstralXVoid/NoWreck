"""Edge: call shapes.

- ``self.method()`` / ``obj.method()`` / ``a.b.c()`` are captured.
- ``super().method()`` / ``f().bar()`` (receiver is a call) are not.
- dunder attributes (``obj.__x__()``) are not.
"""


class Widget:
    def __init__(self, name: str) -> None:
        self.name = name

    def label(self) -> str:
        return self.name.upper()

    def describe(self) -> str:
        return f"{self.prefix()}:{self.label()}"

    def prefix(self) -> str:
        return "W"


class SpecialWidget(Widget):
    def label(self) -> str:
        return super().label() + "!"


def format_widget(widget: Widget) -> str:
    return widget.describe()


def nested_receiver(collection) -> str:
    return collection.first().second()


def chain(registry) -> None:
    registry.get("a").put("b")
    outer.invoke(registry.fetch())


def dunder_call(widget: Widget) -> str:
    return widget.__str__()