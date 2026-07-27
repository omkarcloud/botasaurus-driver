from __future__ import annotations
import os
import time
import types
import typing
from typing import Optional, List, Set, Union, Callable
from ..exceptions import JavascriptRuntimeException, handle_exception, NoSuchElementExistsException

from .element import Element
if typing.TYPE_CHECKING:
    from .browser import Browser, PathLike
from .config import Config
from .. import cdp

__registered__instances__ = set()

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
    profile_directory: Optional[str] = None,
    headless: Optional[bool] = False,
    chrome_executable_path: Optional[str] = None,
    browser_args: Optional[List[str]] = None,
    sandbox: Optional[bool] = True,
    lang: Optional[str] = None,
):
    """
    helper function to launch a browser. it accepts several keyword parameters.
    conveniently, you can just call it bare (no parameters) to quickly launch an instance
    with best practice defaults.
    note: this should be called ```start()```

    :param profile_directory:
    :type profile_directory: str

    :param headless:
    :type headless: bool

    :param chrome_executable_path:
    :type chrome_executable_path: str

    :param browser_args: ["--some-chromeparam=somevalue", "some-other-param=someval"]
    :type browser_args: List[str]

    :param sandbox: default True, but when set to False it adds --no-sandbox to the params, also
    when using linux under a root user, it adds False automatically (else chrome won't start
    :type sandbox: bool

    :param lang: language string
    :type lang: str
    :return:
    """
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


def flatten_frame_tree(
    tree: Union[cdp.page.FrameResourceTree, cdp.page.FrameTree]
):
    yield tree.frame
    if tree.child_frames:
        for child in tree.child_frames:
            yield from flatten_frame_tree(child)


def get_all_param_names(cls):
    comp = cls.mro()
    ret = []
    for c in comp:
        if not hasattr(c, "__annotations__"):
            continue
        for ann in c.__annotations__:
            if ann not in ret:
                ret.append(ann)
    return ret


def cdp_get_module(domain: Union[str, types.ModuleType]):
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

def get_jscode(obj_name):
        js_code_a = (
            """
                           function ___dump(obj, _d = 0) {
                               let _typesA = ['object', 'function'];
                               let _typesB = ['number', 'string', 'boolean'];
                               if (_d == 2) {
                                   console.log('maxdepth reached for ', obj);
                                   return
                               }
                               let tmp = {}
                               for (let k in obj) {
                                   if (obj[k] == window) continue;
                                   let v;
                                   try {
                                       if (obj[k] === null || obj[k] === undefined || obj[k] === NaN) {
                                           console.log('obj[k] is null or undefined or Nan', k, '=>', obj[k])
                                           tmp[k] = obj[k];
                                           continue
                                       }
                                   } catch (e) {
                                       tmp[k] = null;
                                       continue
                                   }
                                   if (_typesB.includes(typeof obj[k])) {
                                       tmp[k] = obj[k]
                                       continue
                                   }
                                   try {
                                       if (typeof obj[k] === 'function') {
                                           tmp[k] = obj[k].toString()
                                           continue
                                       }
                                       if (typeof obj[k] === 'object') {
                                           tmp[k] = ___dump(obj[k], _d + 1);
                                           continue
                                       }
                                   } catch (e) {}
                                   try {
                                       tmp[k] = JSON.stringify(obj[k])
                                       continue
                                   } catch (e) {
                                   }
                                   try {
                                       tmp[k] = obj[k].toString();
                                       continue
                                   } catch (e) {}
                               }
                               return tmp
                           }
                           function ___dumpY(obj) {
                                    if(obj === null || obj === undefined){
                                        return null
                                    }
                                   let _typesB = ['number', 'string', 'boolean'];
                                   if (_typesB.includes(typeof obj)) {
                                       return obj
                                   }                           
                               var objKeys = (obj) => {
                                   var [target, result] = [obj, []];
                                   while (target !== null) {
                                       result = result.concat(Object.getOwnPropertyNames(target));
                                       target = Object.getPrototypeOf(target);
                                   }
                                   return result;
                               }
                               return Object.fromEntries(
                                   objKeys(obj).map(_ => [_, ___dump(obj[_])]))
                           }
                           return ___dumpY( %s )
                   """
            % obj_name
        )
        
        return js_code_a

def wait_for_result(find_func, timeout: Union[int, float] = 10, *args, **kwargs):
        """
        Helper method to implement timeout functionality for find operations
        
        :param find_func: Function that performs the find operation
        :param timeout: Number of seconds to wait before timing out
        :param args: Positional arguments to pass to find_func
        :param kwargs: Keyword arguments to pass to find_func
        :return: Result from find_func or None if timeout occurs
        """
        try:
            now = time.time()
            result = find_func(*args, **kwargs)
            
            if timeout:
                while not result:
                    result = find_func(*args, **kwargs)
                    if time.time() - now > timeout:
                        return None
                    time.sleep(0.5)
            return result
        except NoSuchElementExistsException as e:
          return e.default_value
