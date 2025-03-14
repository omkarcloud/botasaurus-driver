from collections.abc import Mapping as _Mapping, Sequence as _Sequence


class ContraDict(dict):
    """
    directly inherited from dict

    accessible by attribute. o.x == o['x']
    This works also for all corner cases.

    native json.dumps and json.loads work with it

    names like "keys", "update", "values" etc won't overwrite the methods,
    but will just be available using dict lookup notation obj['items'] instead of obj.items

    all key names are converted to snake_case
    hyphen's (-), dot's (.) or whitespaces are replaced by underscore (_)

    autocomplete works even if the objects comes from a list

    recursive action. dict assignments will be converted too.
    """

    __module__ = None

    def __init__(self, *args, **kwargs):
        super().__init__()
        silent = kwargs.pop("silent", False)
        _ = dict(*args, **kwargs)

        # for key, val in dict(*args, **kwargs).items():
        #     _[key] = val
        super().__setattr__("__dict__", self)
        for k, v in _.items():
            _check_key(k, False, silent)
            super().__setitem__(k, _wrap(self.__class__, v))

    def __setitem__(self, key, value):
        super().__setitem__(key, _wrap(self.__class__, value))

    def __setattr__(self, key, value):
        super().__setitem__(key, _wrap(self.__class__, value))

    def __getattribute__(self, attribute):
        if attribute in self:
            return self[attribute]
        if not _check_key(attribute, True, silent=True):
            return getattr(super(), attribute)

        return object.__getattribute__(self, attribute)


def _wrap(cls, v):
    if isinstance(v, _Mapping):
        v = cls(v)

    elif isinstance(v, _Sequence) and not isinstance(
        v, (str, bytes, bytearray, set, tuple)
    ):
        v = [_wrap(cls, x) for x in v]  # Optimized list comprehension
    return v

_warning_names = (
    "items",
    "keys",
    "values",
    "update",
    "clear",
    "copy",
    "fromkeys",
    "get",
    "pop",
    "popitem",
    "setdefault",
    "class",
)
_warning_names_message = """\n\
    While creating a ContraDict object, a key offending key name '{0}' has been found, which might behave unexpected.
    you will only be able to look it up using key, eg. myobject['{0}']. myobject.{0} will not work with that name.
    """


def _check_key(key: str,  boolean: bool = False, silent=False):
    """checks `key` and warns if needed

    :param key:
    :param boolean: return True or False instead of passthrough
    :return:
    """
    e = None
    if not isinstance(key, (str,)):
        if boolean:
            return True
        return key
    if key.lower() in _warning_names or any(_ in key for _ in ("-", ".")):
        if not silent:
            print(_warning_names_message.format(key))
        e = True
    if not boolean:
        return key
    return not e
