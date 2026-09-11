"""Edge: nesting depth and unusual-but-valid formatting.

- Nested functions and nested classes are NOT symbols (documented).
- Two spaces of indentation, blank lines, and comment-only bodies are
  formatting noise the structural hash must ignore.
"""


def outer():  # noqa: D103
  def inner():  # two-space indent, still valid
    return 1

  def deeper():
    def innermost():
      return inner() + 1

    return innermost()

  return deeper()


class Top:
  class Mid:
    def method_in_nested(self):
      return 5

  def direct_method(self):
    return self.__class__.__name__


def trailing():  # comment-only body
  # nothing here
  pass