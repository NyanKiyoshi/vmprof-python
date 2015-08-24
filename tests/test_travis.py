import six
import vmprof
import tempfile


def function_foo():
    return [a for a in six.moves.range(20000000)]


def function_bar():
    return function_foo()


def test_travis_1():
    tmpfile = tempfile.NamedTemporaryFile()
    vmprof.enable(tmpfile.fileno())
    function_foo()
    vmprof.disable()
    assert tmpfile.name