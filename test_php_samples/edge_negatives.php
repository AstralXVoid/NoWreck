<?php

require 'bootstrap.php';
include 'helpers.php';

echo render_head();
print render_body();
list($first, $second) = split_pair();
$copy = array_merge([1], [2]);
$arr = array(1, 2, 3);
$shallow = clone $arr;
$flag = match (true) {
    default => is_ready(),
};
unset($first);
exit(1);

function render_head(): string
{
    // A comment that would look like code: commented_out();
    $text = 'a call inside a string: fake_in_string()';
    $quoted = "interpolated without a call: $text";
    $label = print_r($text, true);
    $ok = isset($text);
    $blank = empty($text);
    die_on_error();
    eval('$doubled = 2 * 2;');
    $magic = $this->__get('x');
    $property = $this->length;
    strlen(...);
    unset($blank);

    return $text . $label . ($ok ? 'y' : 'n') . $blank . $magic . $property;
}
