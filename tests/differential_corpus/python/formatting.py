"""Formatting variety: layout must never change symbol identity.

Audit dimension: structural hash robustness — reformatting and line
shifts are not changes.
"""


def multiline_call(
    first,  # trailing comments on args
    second,
):
    return first + second


class Wide:
    def method(
        self,
        a,
        b,
    ):
        return a - b


def one_liner(): return "short"  # noqa: E701


def spaced_out():

    value = 1


    return value


result = multiline_call(
    1,
    2,
)