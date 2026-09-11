"""Inheritance and mixins: base classes, overrides, super chains."""


class Shape:
    kind = "shape"

    def __init__(self, color: str) -> None:
        self.color = color

    def area(self) -> float:
        raise NotImplementedError

    def describe(self) -> str:
        return f"{self.kind} ({self.color})"


class DrawableMixin:
    def draw(self) -> str:
        return f"drawing {self.describe()}"

    def erase(self) -> str:
        return f"erasing {self.describe()}"


class Circle(Shape, DrawableMixin):
    kind = "circle"

    def __init__(self, color: str, radius: float) -> None:
        super().__init__(color)
        self.radius = radius

    def area(self) -> float:
        return 3.14159 * self.radius * self.radius


class Square(Shape):
    kind = "square"

    def __init__(self, color: str, side: float) -> None:
        super().__init__(color)
        self.side = side

    def area(self) -> float:
        return self.side * self.side


class FancySquare(Square):
    def __init__(self, color: str, side: float, border: float) -> None:
        super().__init__(color, side)
        self.border = border

    def area(self) -> float:
        return super().area() + self.border