from __future__ import annotations
import os
import types
import typing
from typing import Optional, List, Set, Union, Callable

import typing

from ..exceptions import JavascriptRuntimeException, handle_exception

from .element import Element

if typing.TYPE_CHECKING:
    from .browser import Browser, PathLike
from .config import Config
from .. import cdp

__registered__instances__: Set[Browser] = set()

T = typing.TypeVar("T")
# https://stackoverflow.com/questions/38518998/selenium-leaves-behind-running-processes
def close_zombie_processes():
    try:
        pid = True
        while pid:
            pid = os.waitpid(-1, os.WNOHANG)
            try:
                if pid[0] == 0:
                    pid = False
            except:
                pass

    except ChildProcessError:
        pass    


def get_remote_object_value(x,core):
            if x.subtype=="error":
                handle_exception(core, x)
                raise JavascriptRuntimeException(x.description)
            return x.value

def start(
    config: Optional[Config] = None,
    *,
    profile_directory: Optional[PathLike] = None,
    headless: Optional[bool] = False,
    browser_executable_path: Optional[PathLike] = None,
    browser_args: Optional[List[str]] = None,
    sandbox: Optional[bool] = True,
    lang: Optional[str] = None,
) -> Browser:
    """
    helper function to launch a browser. it accepts several keyword parameters.
    conveniently, you can just call it bare (no parameters) to quickly launch an instance
    with best practice defaults.
    note: this should be called ```await start()```

    :param profile_directory:
    :type profile_directory: PathLike

    :param headless:
    :type headless: bool

    :param browser_executable_path:
    :type browser_executable_path: PathLike

    :param browser_args: ["--some-chromeparam=somevalue", "some-other-param=someval"]
    :type browser_args: List[str]

    :param sandbox: default True, but when set to False it adds --no-sandbox to the params, also
    when using linux under a root user, it adds False automatically (else chrome won't start
    :type sandbox: bool

    :param lang: language string
    :type lang: str
    :return:
    """
    if not config:
        config = Config(
            profile_directory,
            headless,
            browser_executable_path,
            browser_args,
            sandbox,
            lang,
        )

    from .browser import Browser
    return Browser.create(config)


def get_registered_instances():
    return __registered__instances__



def deconstruct_browser():
    while __registered__instances__:
        _ = __registered__instances__.pop()
        if not _.stopped:
            _.close()

def filter_recurse_all(
    doc: T, predicate: Callable[[cdp.dom.Node, Element], bool]
) -> List[T]:
    """
    test each child using predicate(child), and return all children for which predicate(child) == True

    :param predicate: a function which takes a node as first parameter and returns a boolean, where True means include
    :return:
    :rtype:
    """
    if not hasattr(doc, "children"):
        raise TypeError("object should have a .children attribute")
    out = []
    if doc and doc.children:
        for child in doc.children:
            if predicate(child):
                # if predicate is True
                out.append(child)
            if child.shadow_roots is not None:
                out.extend(filter_recurse_all(child.shadow_roots[0], predicate))
            out.extend(filter_recurse_all(child, predicate))
            # if result:
            #     out.append(result)
    return out


def filter_recurse(doc: T, predicate: Callable[[cdp.dom.Node, Element], bool]) -> T:
    """
    test each child using predicate(child), and return the first child of which predicate(child) == True

    :param predicate: a function which takes a node as first parameter and returns a boolean, where True means include

    """
    if not hasattr(doc, "children"):
        raise TypeError("object should have a .children attribute")

    if doc and doc.children:
        for child in doc.children:
            if predicate(child):
                # if predicate is True
                return child
            if child.shadow_roots:
                shadow_root_result = filter_recurse(child.shadow_roots[0], predicate)
                if shadow_root_result:
                    return shadow_root_result                    
            result = filter_recurse(child, predicate)
            if result:
                return result

def cdp_get_module(domain: Union[str]):
    """
    get cdp module by given string

    :param domain:
    :type domain:
    :return:
    :rtype:
    """
    import importlib

    if isinstance(domain, types.ModuleType):
        # you get what you ask for
        domain_mod = domain
    else:
        try:
            if domain in ("input",):
                domain = "input_"

            #  fallback if someone passes a str
            domain_mod = getattr(cdp, domain)
            if not domain_mod:
                raise AttributeError
        except AttributeError:
            try:
                domain_mod = importlib.import_module(domain)
            except ModuleNotFoundError:
                raise ModuleNotFoundError(
                    "could not find cdp module from input '%s'" % domain
                )
    return domain_mod
