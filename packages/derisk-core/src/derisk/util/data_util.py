from typing import Callable


def first(*args, default=None):
    def _get_default():
        return default() if default and callable(default) else default

    return next((item for item in args if item), _get_default())
