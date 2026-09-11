"""Edge: code-like text inside strings and comments must be ignored.

Audit dimension: hash/call-capture robustness (strings and comments
must not create phantom symbols or calls).
"""

# Example: def fake_function(): pass
# Example: print("this is not a real call")


def real_function() -> str:
    docstring = """
    def documented_example():
        return "shown in docs, not indexed"
    """
    comment_line = "# def also_fake(): pass"
    sample = "print('nested') and sorted([3, 1])"
    return docstring + comment_line + sample


def calls_only_inside_string() -> None:
    template = "use len(%s) and max(%s) carefully"
    print(template % ("items", "scores"))


def string_with_comment_marker() -> str:
    marker = "value # not a comment"
    return marker.strip()


def fstring_single_quoted() -> str:
    return f'{helper(1)} and {second(2)}'


def fstring_triple_quoted() -> str:
    return f"""
    {third(3)}
    """


def dunder_four_char_attribute() -> object:
    # ``____`` is exactly four characters and is dunder-style under the
    # production rule (``len >= 4``), so the attribute call is excluded.
    return obj.____()