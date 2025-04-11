from __future__ import annotations
import json
import time
import traceback
import typing
from datetime import datetime
from typing import List, Union, Optional

from ..exceptions import handle_exception, NoSuchElementExistsException, ReferenceError, SyntaxError, ElementWithSelectorNotFoundException, DriverException, JavascriptException, ChromeException, InvalidFilenameException, JavascriptSyntaxException, ScreenshotException
from ..driver_utils import create_screenshot_filename, get_download_directory, get_download_filename

from . import element
from . import util
from .config import PathLike
from .connection import Connection
from .. import cdp
from .custom_storage_cdp import block_urls, enable_network


bannedtextsearchresults = set(["title","meta", "script", "link", "style", "head"])
def isbanned(node):
        return node.node_name.lower() in bannedtextsearchresults

def issametype(node, type):
        return node.node_name.lower() == type
def append_safe(results, elem, text, exact_match):
            if exact_match:
                if text == elem.text:
                    results.append(elem)
            else:
                results.append(elem)
              
def make_core_string(SCRIPT, args):
            expression = r"const args = JSON.parse('ARGS'); SCRIPT".replace("SCRIPT", SCRIPT)
            if args is not None:
                expression = expression.replace("ARGS",  json.dumps(args).replace(r'\"', r'\\"'))
            else:
                expression = expression.replace("const args = JSON.parse('ARGS'); ", "")
            return expression             


def make_iife(SCRIPT):
  if SCRIPT is None:
    return None
  return r"""(() => { SCRIPT })()""".replace("SCRIPT", SCRIPT)

class Tab(Connection):
    """
    :ref:`tab` is the controlling mechanism/connection to a 'target',
    for most of us 'target' can be read as 'tab'. however it could also
    be an iframe, serviceworker or background script for example,
    although there isn't much to control for those.

    if you open a new window by using :py:meth:`browser.get(..., new_window=True)`
    your url will open a new window. this window is a 'tab'.
    When you browse to another page, the tab will be the same (it is an browser view).

    So it's important to keep some reference to tab objects, in case you're
    done interacting with elements and want to operate on the page level again.

    Custom CDP commands
    ---------------------------
    Tab object provide many useful and often-used methods. It is also
    possible to utilize the included cdp classes to to something totally custom.

    the cdp package is a set of so-called "domains" with each having methods, events and types.
    to send a cdp method, for example :py:obj:`cdp.page.navigate`, you'll have to check
    whether the method accepts any parameters and whether they are required or not.

    you can use

    ```python
    tab.send(cdp.page.navigate(url='https://yoururlhere'))
    ```

    so tab.send() accepts a generator object, which is created by calling a cdp method.
    this way you can build very detailed and customized commands.
    (note: finding correct command combo's can be a time consuming task, luckily i added a whole bunch
    of useful methods, preferably having the same api's or lookalikes, as in selenium)


    some useful, often needed and simply required methods
    ===================================================================


    :py:meth:`~find`  |  find(text)
    ----------------------------------------
    find and returns a single element by text match. by default returns the first element found.
    much more powerful is the best_match flag, although also much more expensive.
    when no match is found, it will retry for <timeout> seconds (default: 10), so
    this is also suitable to use as wait condition.


    :py:meth:`~find` |  find(text, best_match=True) or find(text, True)
    ---------------------------------------------------------------------------------
    Much more powerful (and expensive!!) than the above, is the use of the `find(text, best_match=True)` flag.
    It will still return 1 element, but when multiple matches are found, picks the one having the
    most similar text length.
    How would that help?
    For example, you search for "login", you'd probably want the "login" button element,
    and not thousands of scripts,meta,headings which happens to contain a string of "login".

    when no match is found, it will retry for <timeout> seconds (default: 10), so
    this is also suitable to use as wait condition.


    :py:meth:`~select` | select(selector)
    ----------------------------------------
    find and returns a single element by css selector match.
    when no match is found, it will retry for <timeout> seconds (default: 10), so
    this is also suitable to use as wait condition.


    :py:meth:`~select_all` | select_all(selector)
    ------------------------------------------------
    find and returns all elements by css selector match.
    when no match is found, it will retry for <timeout> seconds (default: 10), so
    this is also suitable to use as wait condition.


    :py:obj:`Tab`
    ---------------------------
    calling `Tab` will do a lot of stuff under the hood, and ensures all references
    are up to date. also it allows for the script to "breathe", as it is oftentime faster than your browser or
    webpage. So whenever you get stuck and things crashes or element could not be found, you should probably let
    it "breathe"  by calling `Tab`  and/or `Tab.sleep()`

    also, it's ensuring :py:obj:`~url` will be updated to the most recent one, which is quite important in some
    other methods.

    Using other and custom CDP commands
    ======================================================
    using the included cdp module, you can easily craft commands, which will always return an generator object.
    this generator object can be easily sent to the :py:meth:`~send`  method.

    :py:meth:`~send`
    ---------------------------
    this is probably THE most important method, although you won't ever call it, unless you want to
    go really custom. the send method accepts a :py:obj:`cdp` command. Each of which can be found in the
    cdp section.

    when you import * from this package, cdp will be in your namespace, and contains all domains/actions/events
    you can act upon.
    """

    _download_behavior: List[str] = None

    def __init__(
            self,
            websocket_url: str,
            target: cdp.target.TargetInfo,
            browser=None,
            **kwargs,
    ):
        super().__init__(websocket_url, target, browser, **kwargs)
        self.browser = browser

        self.execution_contexts: typing.Dict[str, ExecutionContext] = {}
        # self.execution_contexts: List[ExecutionContext] = []
        self.frames: typing.Dict[str, Frame] = {}
        self._dom = None
        self._window_id = None

        # removed to avoid runtime detection
        # self.add_handler(
        #     cdp.runtime.ExecutionContextCreated, self._execution_contexts_handler
        # )
        # self.add_handler(
        #     cdp.runtime.ExecutionContextDestroyed, self._execution_contexts_handler
        # )
        # self.add_handler(
        #     cdp.runtime.ExecutionContextsCleared, self._execution_contexts_handler
        # )

        # self.add_handler(cdp.page.FrameAttached, self._frame_handler)
        # self.add_handler(cdp.page.FrameDetached, self._frame_handler)
        # self.add_handler(cdp.page.FrameStartedLoading, self._frame_handler)
        # self.add_handler(cdp.page.FrameStoppedLoading, self._frame_handler)

    @property
    def frames_list(self) -> List[Frame]:
        return list(self.frames.values())

    @property
    def execution_contexts_list(self) -> List[ExecutionContext]:
        return list(self.execution_contexts.values())


    def before_request_sent(self, handler):
        """
        Registers a handler to be called when a request is sent.

        Args:
            handler (Callable): A lambda function to handle the request event.
        """
        def handle(event: cdp.network.RequestWillBeSent):
            try:
              handler(event.request_id, event.request, event)
            except:
              traceback.print_exc()
              raise

        self.add_handler(cdp.network.RequestWillBeSent, handle)

    def after_response_received(self, handler):
        """
        Registers a handler to be called when a response is received.

        Args:
            handler (Callable): A lambda function to handle the response event.
        """
        def handle(event: cdp.network.ResponseReceived):
            try:
              handler(event.request_id, event.response, event)
            except:
              traceback.print_exc()
              raise

        self.add_handler(cdp.network.ResponseReceived, handle)

    def _execution_contexts_handler(
        self,
        event: Union[
            cdp.runtime.ExecutionContextsCleared,
            cdp.runtime.ExecutionContextCreated,
            cdp.runtime.ExecutionContextDestroyed,
        ],
        *args,
        **kwargs,
    ):

        if type(event) is cdp.runtime.ExecutionContextCreated:
            context = event.context
            frame_id = context.aux_data.get("frameId")

            try:
                if context.id_ in self.execution_contexts:
                    self.execution_contexts.__dict__.update(**vars(context))
                else:
                    execution_context = ExecutionContext(tab=self, **vars(context))
                    self.execution_contexts[context.unique_id] = execution_context

                frame: Frame = next(filter(lambda key: key == frame_id, self.frames))
                if frame and context.unique_id in self.execution_contexts:
                    self.frames[str(frame_id)].execution_contexts[context.unique_id] = (
                        self.execution_contexts[context.unique_id]
                    )

            except StopIteration:
                frame: None = None
                return

        elif type(event) is cdp.runtime.ExecutionContextDestroyed:
            unique_id = event.execution_context_unique_id
            for frame_id in self.frames.keys():
                try:
                    self.frames[str(frame_id)].execution_contexts.pop(unique_id)
                except KeyError:
                    pass

        elif type(event) is cdp.runtime.ExecutionContextsCleared:
            self.frames.clear()

    def _frame_handler(
        self,
        event: Union[
            cdp.page.FrameAttached,
            cdp.page.FrameDetached,
            cdp.page.FrameStartedLoading,
            cdp.page.FrameStoppedLoading,
        ],
        tab: Tab = None,
    ):
        """

        :param event:
        :type event:
        :return:
        :rtype:
        """
        ev_typ = type(event)
        ev = event

        if ev_typ is cdp.page.FrameAttached:
            try:
                frame = next(filter(lambda fid: ev.frame_id == fid, self.frames))
            except:
                frame = Frame(id_=ev.frame_id, parent_id=ev.parent_frame_id)
                self.frames[str(ev.frame_id)] = frame

            for exid in self.execution_contexts:
                if exid not in frame.execution_contexts:
                    frame.execution_contexts[exid] = self.execution_contexts[exid]
                    frame.loading = True

        if ev_typ is cdp.page.FrameDetached:
            try:
                # frame = next(filter(lambda fid: fid  ==  ev.frame_id, self.frames))
                self.frames.pop(ev.frame_id)
            except (KeyError,):
                pass
            return

        if ev_typ is cdp.page.FrameStartedLoading:
            try:
                frame: Frame = self.frames[ev.frame_id]
                if frame:
                    frame.loading = True

            except (StopIteration, KeyError):
                frame = Frame(id_=ev.frame_id)
                frame.loading = True
                self.frames[str(frame.id_)] = frame

        if ev_typ is cdp.page.FrameStoppedLoading:
            try:
                frame = self.frames[str(ev.frame_id)]
                frame.loading = False
            except (StopIteration, KeyError):
                pass
                # frame.loading = False

    @property
    def inspector_url(self):
        """
        get the inspector url. this url can be used in another browser to show you the devtools interface for
        current tab. useful for debugging (and headless)
        :return:
        :rtype:
        """
        return f"http://{self.browser.config.host}:{self.browser.config.port}/devtools/inspector.html?ws={self.websocket_url[5:]}"

    def open_external_inspector(self):
        """
        opens the system's browser containing the devtools inspector page
        for this tab. could be handy, especially to debug in headless mode.
        """
        import webbrowser

        webbrowser.open(self.inspector_url)

    

    def find(
        self,
        text: str,
        best_match: bool = False,
        return_enclosing_element=True,
        timeout: Union[int, float] = 10,
        type=None, 
        exact_match = False,
    ):
        """
        find single element by text
        can also be used to wait for such element to appear.

        :param text: text to search for. note: script contents are also considered text
        :type text: str
        :param best_match:  :param best_match:  when True (default), it will return the element which has the most
                                               comparable string length. this could help tremendously, when for example
                                               you search for "login", you'd probably want the login button element,
                                               and not thousands of scripts,meta,headings containing a string of "login".
                                               When False, it will return naively just the first match (but is way faster).
         :type best_match: bool
         :param return_enclosing_element:
                 since we deal with nodes instead of elements, the find function most often returns
                 so called text nodes, which is actually a element of plain text, which is
                 the somehow imaginary "child" of a "span", "p", "script" or any other elements which have text between their opening
                 and closing tags.
                 most often we search by text, we actually aim for the element containing the text instead of
                 a lousy plain text node, so by default the containing element is returned.

                 however, there are (why not) exceptions, for example elements that use the "placeholder=" property.
                 this text is rendered, but is not a pure text node. in that case you can set this flag to False.
                 since in this case we are probably interested in just that element, and not it's parent.


                 # todo, automatically determine node type
                 # ignore the return_enclosing_element flag if the found node is NOT a text node but a
                 # regular element (one having a tag) in which case that is exactly what we need.
         :type return_enclosing_element: bool
        :param timeout: raise timeout exception when after this many seconds nothing is found.
        :type timeout: float,int
        """
        return util.wait_for_result(
            self.find_element_by_text,
            timeout,
            text,
            best_match,
            return_enclosing_element,
            type=type,
            exact_match=exact_match
        )
    
    def find_iframe(
        self,
        text: str,
        iframe_elem: element.Element,
        timeout: Union[int, float] = 10,
        type=None,
        exact_match = False,
    ):
        """
        Find single element by text within an iframe
        Can also be used to wait for such element to appear.

        :param text: Text to search for
        :param iframe_elem: Iframe element to search within
        :param timeout: Number of seconds to wait before timing out
        :param type: Type of element to find
        :param exact_match: Whether to match text exactly or partially
        :return: First matching element or None if not found/timeout
        """
        return util.wait_for_result(
            self.find_element_by_text_iframe,
            timeout,
            text,
            iframe_elem,
            type=type,
            exact_match=exact_match
        )    

    def select(
        self,
        selector: str,
        timeout: Union[int, float] = 10,
        _node: Optional[Union[cdp.dom.Node, element.Element]] = None,
    ):
        """
        find single element by css selector.
        can also be used to wait for such element to appear.

        :param selector: css selector, eg a[href], button[class*=close], a > img[src]
        :type selector: str

        :param timeout: raise timeout exception when after this many seconds nothing is found.
        :type timeout: float,int

        """
        return util.wait_for_result(
        self.query_selector,
        timeout,
        selector,
        _node
    )

    def click_at_point(self, x: int, y:int):
            self.send(
                cdp.input_.dispatch_mouse_event("mouseMoved", x=x, y=y)
            )
            time.sleep(0.07)
            self.send(
            cdp.input_.dispatch_mouse_event(
                "mousePressed",
                x=x,
                y=y,
                button=cdp.input_.MouseButton.LEFT,
                click_count=1
            )
            )
            time.sleep(0.09)
            self.send (cdp.input_.dispatch_mouse_event(
                "mouseReleased",
                x=x,
                y=y,
                button=cdp.input_.MouseButton.LEFT,
                click_count=1
            ))
    def perform_get_element_at_point(self,x: int, y:int, raiseError = False):
        try:
          doc: cdp.dom.Node = self.send(cdp.dom.get_document(-1, True))
         # ciel it
          import math
          x = math.ceil(x)
          y = math.ceil(y)
          bid, __, nid = self.send(cdp.dom.get_node_for_location(x=x, y=y, include_user_agent_shadow_dom=False))
        except ChromeException as e:
          if e.message and "No node found" in e.message:
            if raiseError:
                raise
            time.sleep(1)
            return self.perform_get_element_at_point(x,y, True)
          else:
              raise
        

        if nid:
          node = self.send(cdp.dom.describe_node( nid, ))
        else:
            return None
        return element.create(node, self, doc)

    def get_element_at_point(self,x: int, y:int, timeout: Optional[int] = None):
        return util.wait_for_result(
        self.perform_get_element_at_point,
        timeout,
        x,
        y
    )

    def find_all(
        self,
        text: str,
        timeout: Union[int, float] = 10,
        type=None,
        exact_match = False,
    ):
        """
        find multiple elements by text
        can also be used to wait for such element to appear.

        :param text: text to search for. note: script contents are also considered text
        :type text: str

        :param timeout: raise timeout exception when after this many seconds nothing is found.
        :type timeout: float,int
        """
        return util.wait_for_result(
        self.find_elements_by_text,
        timeout,
        text,
        type=type,
        exact_match=exact_match
    ) or []
    def find_all_iframe(
        self,
        text: str,
        iframe_elem: element.Element,
        timeout: Union[int, float] = 10,
        type=None,
        exact_match = False,
    ):
        """
        Find multiple elements by text within an iframe
        Can also be used to wait for such elements to appear.

        :param text: Text to search for
        :param iframe_elem: Iframe element to search within
        :param timeout: Number of seconds to wait before timing out
        :param type: Type of elements to find
        :param exact_match: Whether to match text exactly or partially
        :return: List of matching elements or empty list if not found/timeout
        """
        return util.wait_for_result(
            self.find_elements_by_text_iframe,
            timeout,
            text,
            iframe_elem,
            type=type,
            exact_match=exact_match
        ) or []    
    
    def select_all(
        self,
        selector: str,
        timeout: Union[int, float] = 10,
        node_name = None,
        _node: Optional[Union[cdp.dom.Node, element.Element]] = None,
        
    ):
        """
        find multiple elements by css selector.
        can also be used to wait for such element to appear.

        :param selector: css selector, eg a[href], button[class*=close], a > img[src]
        :type selector: str
        :param timeout: raise timeout exception when after this many seconds nothing is found.
        :type timeout: float,int
        """

        results = util.wait_for_result(
            self.query_selector_all,
            timeout,
            selector,
            _node
        )
        
        if not results:
            return []
            
        return [item for item in results if item.node.node_name.lower() == node_name.lower()] if node_name else results

    def count_select(
        self,
        selector: str,
        timeout: Union[int, float] = 10,
        node_name = None,
        _node: Optional[Union[cdp.dom.Node, element.Element]] = None,
        
    ):
        """
        find multiple elements by css selector.
        can also be used to wait for such element to appear.

        :param selector: css selector, eg a[href], button[class*=close], a > img[src]
        :type selector: str
        :param timeout: raise timeout exception when after this many seconds nothing is found.
        :type timeout: float,int
        """

        return util.wait_for_result(
        self.query_selector_count,
        timeout,
        selector,
        _node
    ) or 0

    def query_selector_all(
        self,
        selector: str,
        _node: Optional[Union[cdp.dom.Node, "element.Element"]] = None,
    ):
        """
        equivalent of javascripts document.querySelectorAll.
        this is considered one of the main methods to use in this package.

        it returns all matching :py:obj:`nodriver.Element` objects.

        :param selector: css selector. (first time? => https://www.w3schools.com/cssref/css_selectors.php )
        :type selector: str
        :param _node: internal use
        :type _node:
        :return:
        :rtype:
        """

        if not _node:
            doc: cdp.dom.Node = self.send(cdp.dom.get_document(-1, True))
        else:
            doc = _node
            if _node.node_name == "IFRAME":
                doc = _node.content_document
        node_ids = []

        try:
            node_ids = self.send(
                cdp.dom.query_selector_all(doc.node_id, selector)
            )
        except AttributeError:
            # has no content_document
            return

        except ChromeException as e:
            is_no_node = "could not find node" in e.message.lower()
            if _node is not None:
                if is_no_node:
                    is_last = getattr(_node, "is_last")
                    if is_last:
                        raise NoSuchElementExistsException([])
                    # if supplied node is not found, the dom has changed since acquiring the element
                    # therefore we need to update our passed node and try again
                    _node.update()
                    _node.is_last =  True  # make sure this isn't turned into infinite loop
                    return self.query_selector_all(selector, _node)
            else:
                # TODO: Why, i guess removable maybe
                self.send(cdp.dom.disable())
                if is_no_node:
                    # simply means that doc was destroyed in navigation
                    return []
                raise
        if not node_ids:
            return []
        results = []

        for nid in node_ids:
            node = util.filter_recurse(doc, lambda n: n.node_id == nid)
            # we pass along the retrieved document tree,
            # to improve performance
            if not node:
                continue
            elem = element.create(node, self, doc)
            results.append(elem)
        return results

    def query_selector_count(
        self,
        selector: str,
        _node: Optional[Union[cdp.dom.Node, "element.Element"]] = None,
    ):
        """
        equivalent of javascripts document.querySelectorAll.
        this is considered one of the main methods to use in this package.


        :param selector: css selector. (first time? => https://www.w3schools.com/cssref/css_selectors.php )
        :type selector: str
        :param _node: internal use
        :type _node:
        :return:
        :rtype:
        """

        if not _node:
            doc: cdp.dom.Node = self.send(cdp.dom.get_document(-1, True))
        else:
            doc = _node
            if _node.node_name == "IFRAME":
                doc = _node.content_document
        node_ids = []

        try:
            node_ids = self.send(
                cdp.dom.query_selector_all(doc.node_id, selector)
            )
            

        except ChromeException as e:
            is_no_node = "could not find node" in e.message.lower()
            if _node is not None:
                if is_no_node:
                    is_last = getattr(_node, "is_last")
                    if is_last:
                        raise NoSuchElementExistsException(0)
                    # if supplied node is not found, the dom has changed since acquiring the element
                    # therefore we need to update our passed node and try again
                    _node.update()
                    _node.is_last =  True  # make sure this isn't turned into infinite loop
                    return self.query_selector_count(selector, _node)
            else:
                # TODO: Why, i guess removable maybe
                self.send(cdp.dom.disable())
                if is_no_node:
                    # simply means that doc was destroyed in navigation
                    return 0  # Return 0 instead of an empty list
                raise
        if not node_ids:
            return 0
        else:
            return len(node_ids)


    def query_selector(
        self,
        selector: str,
        _node: Optional[Union[cdp.dom.Node, element.Element]] = None,
    ):
        """
        find single element based on css selector string

        :param selector: css selector(s)
        :type selector: str
        :return:
        :rtype:
        """
        selector = selector.strip()

        if not _node:
            doc: cdp.dom.Node = self.send(cdp.dom.get_document(-1, True))
        else:
            doc = _node
            if _node.node_name == "IFRAME":
                doc = _node.content_document
        node_id = None
        if not doc:
            raise DriverException("Failed to find Document")
        try:
            node_id = self.send(cdp.dom.query_selector(doc.node_id, selector))
        except ChromeException as e:
            is_no_node = "could not find node" in e.message.lower()
            if _node is not None:
                if is_no_node:
                    is_last = getattr(_node, "is_last")
                    if is_last:
                        raise NoSuchElementExistsException(None)
                    # if supplied node is not found, the dom has changed since acquiring the element
                    # therefore we need to update our passed node and try again
                    _node.update()
                    _node.is_last =  True  # make sure this isn't turned into infinite loop
                    return self.query_selector(selector, _node)
            else:
                self.send(cdp.dom.disable())
                if is_no_node:
                    # simply means that doc was destroyed in navigation
                    return []
                raise
        if not node_id:
            return
        node = util.filter_recurse(doc, lambda n: n.node_id == node_id)
        if not node:
            return
        return element.create(node, self, doc)

        
    def find_element_by_text(
        self,
        text: str,
        best_match: Optional[bool] = False,
        return_enclosing_element: Optional[bool] = True,
        type=None,
        exact_match= False,
    ) -> Union[element.Element, None]:
        """
        finds and returns the first element containing <text>, or best match

        :param text:
        :type text:
        :param best_match:  when True, which is MUCH more expensive (thus much slower),
                            will find the closest match based on length.
                            this could help tremendously, when for example you search for "login", you'd probably want the login button element,
                            and not thousands of scripts,meta,headings containing a string of "login".

        :type best_match: bool
        :param return_enclosing_element:
        :type return_enclosing_element:
        :return:
        :rtype:
        """
        doc = self.send(cdp.dom.get_document(-1, True))
        search_id, nresult = self.send(cdp.dom.perform_search(text, True))
        # Not Found, Exit
        if nresult:
            node_ids = self.send(cdp.dom.get_search_results(search_id, 0, nresult))
        else:
            node_ids = []

        self.send(cdp.dom.discard_search_results(search_id))

        if not node_ids:
            return None  # Fix: Return None if no nodes are found

        results = []
        for nid in node_ids:
            # Added as just need this this nullifies best match
            if results:
                return results[0]

            node = util.filter_recurse(doc, lambda n: n.node_id == nid)
            try:
                elem = element.create(node, self, doc)
            except:  # noqa
                continue
            self.checktextnodeandappend(type, results, elem, text, exact_match)   
            if results:
                self.send(cdp.dom.disable())
                return results[0]
        
        self.send(cdp.dom.disable())
        return None  # Fix: Return None if no results are found

    def find_elements_by_text(
        self,
        text: str,
        tag_hint: Optional[str] = None,
        type=None,
        exact_match = False,
    ) -> List[element.Element]:
        """
        returns element which match the given text.
        please note: this may (or will) also return any other element (like inline scripts),
        which happen to contain that text.

        :param text:
        :type text:
        :param tag_hint: when provided, narrows down search to only elements which match given tag eg: a, div, script, span
        :type tag_hint: str
        :return:
        :rtype:
        """

        doc = self.send(cdp.dom.get_document(-1, True))
        search_id, nresult = self.send(cdp.dom.perform_search(text, True))
        if nresult:
            node_ids = self.send(
                cdp.dom.get_search_results(search_id, 0, nresult)
            )
        else:
            node_ids = []

        self.send(cdp.dom.discard_search_results(search_id))

        results = []
        for nid in node_ids:
            node = util.filter_recurse(doc, lambda n: n.node_id == nid)
            if not node:
                node = self.send(cdp.dom.resolve_node(node_id=nid))
                if not node:
                    continue
                # remote_object = self.send(cdp.dom.resolve_node(backend_node_id=node.backend_node_id))
                # node_id = self.send(cdp.dom.request_node(object_id=remote_object.object_id))
            try:
                elem = element.create(node, self, doc)
            except:  # noqa
                continue
            self.checktextnodeandappend(type, results, elem, text, exact_match)  

        self.send(cdp.dom.disable())
        return results  # Fix: Return results directly
    
    def _find_text_nodes_in_iframe(self, text, iframe_elem, type, exact_match, single_result=False):
        """
        Common method to find text nodes in an iframe and process them.
        """
        results = []
        if iframe_elem.content_document:
            iframe_text_nodes = util.filter_recurse_all(
                iframe_elem,
                lambda node: node.node_type == 3  # noqa
                and text.lower() in node.node_value.lower(),
            )
            if iframe_text_nodes:
                for text_node in iframe_text_nodes:
                    elem = element.create(text_node, self, iframe_elem.tree)
                    self.checktextnodeandappend(type, results, elem, text, exact_match)
                    if single_result and results:
                        self.send(cdp.dom.disable())
                        return results[0]  # Return first match immediately if requested

        self.send(cdp.dom.disable())
        return results if not single_result else None

    def find_elements_by_text_iframe(
        self,
        text: str,
        iframe_elem: element.Element,
        tag_hint: Optional[str] = None,
        type=None,
        exact_match=False,
    ) -> List[element.Element]:
        return self._find_text_nodes_in_iframe(text, iframe_elem, type, exact_match)

    def find_element_by_text_iframe(
        self,
        text: str,
        iframe_elem: element.Element,
        tag_hint: Optional[str] = None,
        type=None,
        exact_match=False,
    ) -> Optional[element.Element]:
        return self._find_text_nodes_in_iframe(text, iframe_elem, type, exact_match, single_result=True)

    def run_cdp_command(self, command):
        return self.send(command)

    def back(self):
        """
        history back
        """
        self.send(cdp.runtime.evaluate("window.history.back()"))

    def forward(self):
        """
        history forward
        """
        self.send(cdp.runtime.evaluate("window.history.forward()"))

    def reload(
        self,
        ignore_cache: Optional[bool] = True,
        script_to_evaluate_on_load: Optional[str] = None,
    ):
        """
        Reloads the page

        :param ignore_cache: when set to True (default), it ignores cache, and re-downloads the items
        :type ignore_cache:
        :param script_to_evaluate_on_load: script to run on load. I actually haven't experimented with this one, so no guarantees.
        :type script_to_evaluate_on_load:
        :return:
        :rtype:
        """
        self.send(
            cdp.page.reload(
                ignore_cache=ignore_cache,
                script_to_evaluate_on_load=script_to_evaluate_on_load,
            ),
        )


    def checktextnodeandappend(self, type, results, elem, text, exact_match):
        if elem.node_type == 3:
                # if found element is a text node (which is plain text, and useless for our purpose),
                # we return the parent element of the node (which is often a tag which can have text between their
                # opening and closing tags (that is most tags, except for example "img" and "video", "br")
            if not elem.parent:
                    # check if parent actually has a parent and update it to be absolutely sure
                elem.update()
            final = elem.parent or elem
            if final:
                if type:
                    if issametype(final.node, type):
                        append_safe(results, final, text, exact_match)
                else:
                    if not isbanned(final.node):
                        append_safe(results, final, text, exact_match)
        else:
                if type:
                    if issametype(elem.node,type):
                        append_safe(results, elem, text, exact_match)
                else:
                    if not isbanned(elem.node):
                        append_safe(results, elem, text, exact_match)


    def evaluate(
        self, expression: str, args=None, await_promise=False, return_by_value=True
    ):
        core = make_core_string(expression, args)
        expression = r"""(() => {
const resp = (() => { CORE })()
if (resp instanceof Promise) {
    return new Promise((resolve, reject) => {
        return resp.then(x => resolve(JSON.stringify({ "x": x }))).catch(reject)
    })
} else {
    return JSON.stringify({ "x": resp })
}
})()""".replace("CORE", core)
        response = self.send(
            cdp.runtime.evaluate(
                expression=expression,
                user_gesture=True,
                await_promise=await_promise,
                return_by_value=return_by_value,
            )
        )

        if not response:
            raise JavascriptSyntaxException()

        remote_object, errors = response
        if errors:
            handle_exception(core, errors.exception)
            raise JavascriptException(errors)
        if remote_object:
            if return_by_value:
                if remote_object.value:
                    return json.loads(util.get_remote_object_value(remote_object, core)).get("x")

            else:
                return remote_object, errors
    def js_dumps(
        self, obj_name: str, return_by_value: Optional[bool] = True
    ) -> typing.Union[
        typing.Dict,
        typing.Tuple[cdp.runtime.RemoteObject, cdp.runtime.ExceptionDetails],
    ]:
        """
        dump given js object with its properties and values as a dict

        note: complex objects might not be serializable, therefore this method is not a "source of thruth"

        :param obj_name: the js object to dump
        :type obj_name: str

        :param return_by_value: if you want an tuple of cdp objects (returnvalue, errors), set this to False
        :type return_by_value: bool

        example
        ------

        x = self.js_dumps('window')
        print(x)
            '...{
            'pageYOffset': 0,
            'visualViewport': {},
            'screenX': 10,
            'screenY': 10,
            'outerWidth': 1050,
            'outerHeight': 832,
            'devicePixelRatio': 1,
            'screenLeft': 10,
            'screenTop': 10,
            'styleMedia': {},
            'onsearch': None,
            'isSecureContext': True,
            'trustedTypes': {},
            'performance': {'timeOrigin': 1707823094767.9,
            'timing': {'connectStart': 0,
            'navigationStart': 1707823094768,
            ]...
            '
        """
        js_code_a = util.get_jscode(obj_name)
        # we're purposely not calling self.evaluate here to prevent infinite loop on certain expressions
        return self.evaluate(js_code_a, None, True,return_by_value )
     

    def close(self):
        """
        close the current target (ie: tab,window,page)
        :return:
        :rtype:
        """
        if not self.is_closed:
            self.is_closed = True
            if self.target and self.target.target_id:
                self.send(cdp.target.close_target(target_id=self.target.target_id))

            self.close_connections()
            
    def get_window(self):
        """
        get the window Bounds
        :return:
        :rtype:
        """
        window_id, bounds = self.send(
            cdp.browser.get_window_for_target(self.target.target_id)
        )
        return window_id, bounds
    def get_content(self):
        """
        gets the current page source content (html)
        :return:
        :rtype:
        """
        doc: cdp.dom.Node = self.send(cdp.dom.get_document(-1, True))
        return self.send(
            cdp.dom.get_outer_html(backend_node_id=doc.backend_node_id)
        )

    def maximize(self):
        """
        maximize page/tab/window
        """
        return self.set_window_state(state="maximize")

    def minimize(self):
        """
        minimize page/tab/window
        """
        return self.set_window_state(state="minimize")

    def fullscreen(self):
        """
        minimize page/tab/window
        """
        return self.set_window_state(state="fullscreen")

    def normal(self):
        return self.set_window_state(state="normal")

    def set_window_size(self, left=0, top=0, width=1280, height=1024):
        """
        set window size and position

        :param left: pixels from the left of the screen to the window top-left corner
        :type left:
        :param top: pixels from the top of the screen to the window top-left corner
        :type top:
        :param width: width of the window in pixels
        :type width:
        :param height: height of the window in pixels
        :type height:
        :return:
        :rtype:
        """
        return self.set_window_state(left, top, width, height)

    def activate(self):
        """
        active this target (ie: tab,window,page)
        """
        self.send(cdp.target.activate_target(self.target.target_id))

    def bring_to_front(self):
        """
        alias to self.activate
        """
        self.activate()

    def set_window_state(
        self, left=0, top=0, width=1280, height=720, state="normal"
    ):
        """
        sets the window size or state.

        for state you can provide the full name like minimized, maximized, normal, fullscreen, or
        something which leads to either of those, like min, mini, mi,  max, ma, maxi, full, fu, no, nor
        in case state is set other than "normal", the left, top, width, and height are ignored.

        :param left:
            desired offset from left, in pixels
        :type left: int

        :param top:
            desired offset from the top, in pixels
        :type top: int

        :param width:
            desired width in pixels
        :type width: int

        :param height:
            desired height in pixels
        :type height: int

        :param state:
            can be one of the following strings:
                - normal
                - fullscreen
                - maximized
                - minimized

        :type state: str

        """
        available_states = ["minimized", "maximized", "fullscreen", "normal"]
        window_id: cdp.browser.WindowID
        bounds: cdp.browser.Bounds
        (window_id, bounds) = self.get_window()

        for state_name in available_states:
            if all(x in state_name for x in state.lower()):
                break
        else:
            raise NameError(
                "could not determine any of %s from input '%s'"
                % (",".join(available_states), state)
            )
        window_state = getattr(
            cdp.browser.WindowState, state_name.upper(), cdp.browser.WindowState.NORMAL
        )
        if window_state == cdp.browser.WindowState.NORMAL:
            bounds = cdp.browser.Bounds(left, top, width, height, window_state)
        else:
            # min, max, full can only be used when current state == NORMAL
            # therefore we first switch to NORMAL
            self.set_window_state(state="normal")
            bounds = cdp.browser.Bounds(window_state=window_state)

        self.send(cdp.browser.set_window_bounds(window_id, bounds=bounds))

    def scroll_down(self, amount=25):
        """
        scrolls down maybe

        :param amount: number in percentage. 25 is a quarter of page, 50 half, and 1000 is 10x the page
        :type amount: int
        :return:
        :rtype:
        """
        window_id: cdp.browser.WindowID
        bounds: cdp.browser.Bounds
        (window_id, bounds) = self.get_window()

        self.send(
            cdp.input_.synthesize_scroll_gesture(
                x=0,
                y=0,
                y_distance=-(bounds.height * (amount / 100)),
                y_overscroll=0,
                x_overscroll=0,
                prevent_fling=True,
                repeat_delay_ms=0,
                speed=7777,
            )
        )

    def scroll_up(self, amount=25):
        """
        scrolls up maybe

        :param amount: number in percentage. 25 is a quarter of page, 50 half, and 1000 is 10x the page
        :type amount: int

        :return:
        :rtype:
        """
        window_id: cdp.browser.WindowID
        bounds: cdp.browser.Bounds
        (window_id, bounds) = self.get_window()

        self.send(
            cdp.input_.synthesize_scroll_gesture(
                x=0,
                y=0,
                y_distance=(bounds.height * (amount / 100)),
                x_overscroll=0,
                prevent_fling=True,
                repeat_delay_ms=0,
                speed=7777,
            )
        )

    def wait(self, t: Union[int, float] = None):
        tree = self.get_frame_tree()
        tree_map = {str(f.id_): f for f in util.flatten_frame_tree(tree)}
        for frame_id in tree_map:
            if frame_id in self.frames:
                self.frames[frame_id].__dict__.update(tree_map[frame_id].__dict__)
        super().wait(t)

    def wait_for(
        self,
        selector: Optional[str] = "",
        text: Optional[str] = "",
        timeout: Optional[Union[int, float]] = 10,
    ) -> element.Element:
        """
        variant on query_selector_all and find_elements_by_text
        this variant takes either selector or text, and will block until
        the requested element(s) are found.

        it will block for a maximum of <timeout> seconds, after which
        an TimeoutError will be raised

        :param selector: css selector
        :type selector:
        :param text: text
        :type text:
        :param timeout:
        :type timeout:
        :return:
        :rtype: Element
        """
        now = time.time()
        if selector:
            item = self.query_selector(selector)
            
            while not item:
                item = self.query_selector(selector)
                if time.time() - now > timeout:
                    # Raise Exception if it is not found till this time
                    raise ElementWithSelectorNotFoundException(selector)
                self.sleep(0.5)
                # self.sleep(0.5)
            return item
        if text:
            item = self.find_element_by_text(text)
            while not item:
                item = self.find_element_by_text(text)
                if time.time() - now > timeout:
                    raise ElementWithSelectorNotFoundException(text)
                self.sleep(0.5)
            return item
    def download_file(self, url: str, filename: Optional[PathLike] = None, _node = None):
        """
        downloads file by given url.

        :param url: url of the file
        :param filename: the name for the file. if not specified the name is composed from the url file name
        """
        if not self._download_behavior:
            directory_path = get_download_directory()
            self.set_download_path(directory_path)

        filename = filename if filename else datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        code = r"""
         (elem) => {
            async function _downloadFile(
              imageSrc,
              nameOfDownload, 
            ) {
              const response = await fetch(imageSrc);
              const blobImage = await response.blob();
              let downloadName = nameOfDownload;
              
              const href = URL.createObjectURL(blobImage);
              const anchorElement = document.createElement('a');
              anchorElement.href = href;
              anchorElement.download = downloadName;
              document.body.appendChild(anchorElement);
              anchorElement.click();

              setTimeout(() => {
                document.body.removeChild(anchorElement);
                window.URL.revokeObjectURL(href);
                }, 500);
            }
            _downloadFile('__URL', '__FILENAME')
            }
            """.replace('__URL', url).replace('__FILENAME', filename)
      
        body = self.query_selector("body", _node)
        body.update()
        self.send(
            cdp.runtime.call_function_on(
                code,
                object_id=body.object_id,
                arguments=[cdp.runtime.CallArgument(object_id=body.object_id)],
            )
        )
        filename, relative_path = get_download_filename(filename)
        print(f"View downloaded file at {relative_path}")
        

    def save_screenshot(
        self,
        filename: Optional[PathLike] = "auto",
        format: Optional[str] = "png",
        full_page: Optional[bool] = False,
    ) -> str:
        """
        Saves a screenshot of the page.
        This is not the same as :py:obj:`Element.save_screenshot`, which saves a screenshot of a single element only

        :param filename: uses this as the save path
        :type filename: PathLike
        :param format: jpeg or png (defaults to jpeg)
        :type format: str
        :param full_page: when False (default) it captures the current viewport. when True, it captures the entire page
        :type full_page: bool
        :return: the path/filename of saved screenshot
        :rtype: str
        """
        # noqa

        self.sleep()  # update the target's url
        if not filename:
            raise InvalidFilenameException(filename)

        filename, relative_path = create_screenshot_filename(filename)
        path = filename

        if format.lower() in ["jpg", "jpeg"]:
            ext = ".jpg"
            format = "jpeg"

        elif format.lower() in ["png"]:
            ext = ".png"
            format = "png"

        
        data = self.send(
            cdp.page.capture_screenshot(format_=format, capture_beyond_viewport=True)
        )
        if not data:
            raise ScreenshotException()
        import base64

        data_bytes = base64.b64decode(data)
        with open(path, "wb") as file:
            file.write(data_bytes)

        print(f"View screenshot at {relative_path}")
        return str(path)

    def set_download_path(self, path: PathLike):
        """
        sets the download path and allows downloads
        this is required for any download function to work (well not entirely, since when unset we set a default folder)

        :param path:
        :type path:
        :return:
        :rtype:
        """
        self.send(
            cdp.browser.set_download_behavior(
                behavior="allow", download_path=path
            )
        )
        self._download_behavior = ["allow", path]
    def get_all_linked_sources(self):
        """
        get all elements of tag: link, a, img, scripts meta, video, audio

        :return:
        """
        all_assets = self.query_selector_all(selector="a,link,img,script,meta")
        return [element.create(asset, self) for asset in all_assets]

    def get_all_urls(self, absolute=True) -> List[str]:
        """
        convenience function, which returns all links (a,link,img,script,meta)

        :param absolute: try to build all the links in absolute form instead of "as is", often relative
        :return: list of urls
        """

        import urllib.parse

        res = []
        all_assets = self.query_selector_all(selector="a,link,img,script,meta")
        for asset in all_assets:
            if not absolute:
                res.append(asset.src or asset.href)
            else:
                for k, v in asset.attrs.items():
                    if k in ("src", "href"):
                        if "#" in v:
                            continue
                        if not any([_ in v for _ in ("http", "//", "/")]):
                            continue
                        abs_url = urllib.parse.urljoin(
                            "/".join(self.url.rsplit("/")[:3]), v
                        )
                        if not abs_url.startswith(("http", "//", "ws")):
                            continue
                        res.append(abs_url)
        return res

    def __call__(
        self,
        text: Optional[str] = "",
        selector: Optional[str] = "",
        timeout: Optional[Union[int, float]] = 10,
    ):
        """
        alias to query_selector_all or find_elements_by_text, depending
        on whether text= is set or selector= is set

        :param selector: css selector string
        :type selector: str
        :return:
        :rtype:
        """
        return self.wait_for(text, selector, timeout)

    def get_frame_tree(self) -> cdp.page.FrameTree:
        """
        retrieves the frame tree for current tab
        There seems no real difference between :ref:`Tab.get_frame_resource_tree()`
        :return:
        :rtype:
        """
        tree: cdp.page.FrameTree = super().send(cdp.page.get_frame_tree())
        return tree

    def get_frame_resource_tree(self) -> cdp.page.FrameResourceTree:
        """
        retrieves the frame resource tree for current tab.
        There seems no real difference between :ref:`Tab.get_frame_tree()`
        but still it returns a different object
        :return:
        :rtype:
        """
        tree: cdp.page.FrameResourceTree = self.send(cdp.page.get_resource_tree())
        return tree

    def get_frame_resource_urls(self):
        """
        gets the
        :param urls_only:
        :type urls_only:
        :return:
        :rtype:
        """
        import functools
        _tree = self.get_frame_resource_tree()
        return functools.reduce(
            lambda a, b: a + b[1], util.flatten_frame_tree(_tree), []
        )

    def search_frame_resources(self, query: str):
        list_of_tuples = self.get_frame_resource_urls()
        tasks = []
        for frame_id, urls in list_of_tuples:
            for url in urls:
                tasks.append(
                    self.send(
                        cdp.page.search_in_resource(
                            frame_id=cdp.page.FrameId(frame_id), url=url, query=query
                        )
                    )
                )
        return tasks

    def bypass_insecure_connection_warning(self):
        """
        when you enter a site where the certificate is invalid
        you get a warning. call this function to "proceed"
        :return:
        :rtype:
        """
        body = self.select("body")
        body.send_keys("thisisunsafe")

    def mouse_move(self, x: float, y: float, steps=10, flash=False):
        self.send(cdp.input_.dispatch_mouse_event("mouseMoved", x=x, y=y))
        # steps = 1 if (not steps or steps < 1) else steps
        # # probably the worst waay of calculating this. but couldn't think of a better solution today.
        # if steps > 1:
        #     step_size_x = x // steps
        #     step_size_y = y // steps
        #     pathway = [(step_size_x * i, step_size_y * i) for i in range(steps + 1)]
        #     for point in pathway:
        #         if flash:
        #             self.flash_point(point[0], point[1])
        #         self.send(
        #             cdp.input_.dispatch_mouse_event(
        #                 "mouseMoved", x=point[0], y=point[1]
        #             )
        #         )
        # else:
        #     self.send(cdp.input_.dispatch_mouse_event("mouseMoved", x=x, y=y))
        # if flash:
        #     self.flash_point(x, y)
        # else:
        #     self.sleep(0.05)
        # self.send(cdp.input_.dispatch_mouse_event("mouseReleased", x=x, y=y))
        # if flash:
        #     self.flash_point(x, y)

    def mouse_click(
        self,
        x: float,
        y: float,
        button: str = "left",
        buttons: typing.Optional[int] = 1,
        modifiers: typing.Optional[int] = 0,
        _until_event: typing.Optional[type] = None,
    ):
        """native click on position x,y
        :param y:
        :type y:
        :param x:
        :type x:
        :param button: str (default = "left")
        :param buttons: which button (default 1 = left)
        :param modifiers: *(Optional)* Bit field representing pressed modifier keys.
                Alt=1, Ctrl=2, Meta/Command=4, Shift=8 (default: 0).
        :param _until_event: internal. event to wait for before returning
        :return:
        """

        self.send(
            cdp.input_.dispatch_mouse_event(
                "mousePressed",
                x=x,
                y=y,
                modifiers=modifiers,
                button=cdp.input_.MouseButton(button),
                buttons=buttons,
                click_count=1,
            )
        )

        self.send(
            cdp.input_.dispatch_mouse_event(
                "mouseReleased",
                x=x,
                y=y,
                modifiers=modifiers,
                button=cdp.input_.MouseButton(button),
                buttons=buttons,
                click_count=1,
            )
        )

    def mouse_drag(
        self,
        source_point: tuple[float, float],
        dest_point: tuple[float, float],
        relative: bool = False,
        steps: int = 1,
    ):
        """
        drag mouse from one point to another. holding button pressed
        you are probably looking for :py:meth:`element.Element.mouse_drag` method. where you
        can drag on the element

        :param dest_point:
        :type dest_point:
        :param source_point:
        :type source_point:
        :param relative: when True, treats point as relative. for example (-100, 200) will move left 100px and down 200px
        :type relative:

        :param steps: move in <steps> points, this could make it look more "natural" (default 1),
               but also a lot slower.
               for very smooth action use 50-100
        :type steps: int
        :return:
        :rtype:
        """
        if relative:
            dest_point = (
                source_point[0] + dest_point[0],
                source_point[1] + dest_point[1],
            )
        self.send(
            cdp.input_.dispatch_mouse_event(
                "mousePressed",
                x=source_point[0],
                y=source_point[1],
                button=cdp.input_.MouseButton("left"),
            )
        )
        steps = 1 if (not steps or steps < 1) else steps

        # if steps == 1:
        #     self.send(
        #         cdp.input_.dispatch_mouse_event(
        #             "mouseMoved", x=dest_point[0], y=dest_point[1]
        #         )
        #     )
        # elif steps > 1:
        #     # probably the worst waay of calculating this. but couldn't think of a better solution today.
        #     step_size_x = (dest_point[0] - source_point[0]) / steps
        #     step_size_y = (dest_point[1] - source_point[1]) / steps
        #     pathway = [
        #         (source_point[0] + step_size_x * i, source_point[1] + step_size_y * i)
        #         for i in range(steps + 1)
        #     ]
        #     for point in pathway:
        #         self.send(
        #             cdp.input_.dispatch_mouse_event(
        #                 "mouseMoved",
        #                 x=point[0],
        #                 y=point[1],
        #             )
        #         )
        #         time.sleep(0)

        self.send(
            cdp.input_.dispatch_mouse_event(
                type_="mouseReleased",
                x=dest_point[0],
                y=dest_point[1],
                button=cdp.input_.MouseButton("left"),
            )
        )

    def flash_point(self, x, y, duration=0.5, size=10):
        import secrets
        style = (
            "position:absolute;z-index:99999999;padding:0;margin:0;"
            "left:{:.1f}px; top: {:.1f}px;"
            "opacity:1;"
            "width:{:d}px;height:{:d}px;border-radius:50%;background:red;"
            "animation:show-pointer-ani {:.2f}s ease 1;"
        ).format(x - 8, y - 8, size, size, duration)
        script = (
            """
                var css = document.styleSheets[0];
                for( let css of [...document.styleSheets]) {{
                    try {{
                        css.insertRule(`
                        @keyframes show-pointer-ani {{
                              0% {{ opacity: 1; transform: scale(1, 1);}}
                              50% {{ transform: scale(3, 3);}}
                              100% {{ transform: scale(1, 1); opacity: 0;}}
                        }}`,css.cssRules.length);
                        break;
                    }} catch (e) {{
                        console.log(e)
                    }}
                }};
                var _d = document.createElement('div');
                _d.style = `{0:s}`;
                _d.id = `{1:s}`;
                document.body.insertAdjacentElement('afterBegin', _d);
    
                setTimeout( () => document.getElementById('{1:s}').remove(), {2:d});
    
            """.format(
                style, secrets.token_hex(8), int(duration * 1000)
            )
            .replace("  ", "")
            .replace("\n", "")
        )
        self.send(
            cdp.runtime.evaluate(
                script,
                await_promise=True,
                user_gesture=True,
            )
        )


    def block_urls(self, urls) -> None:
        # You usually don't need to close it because we automatically close it when script is cancelled (ctrl + c) or completed
        self.send(enable_network())
        self.send(block_urls(urls))

    def block_images_and_css(self) -> None:
        images_and_css_patterns = [
                ".css",
                ".jpg",
                ".jpeg",
                ".png",
                ".webp",
                ".svg",
                ".gif",
                ".woff",
                ".pdf",
                ".zip",
                ".ico",
            ]
    
        self.block_urls(
            images_and_css_patterns
        )

    def block_images(self) -> None:
        images_patterns = [
                ".jpg",
                ".jpeg",
                ".png",
                ".webp",
                ".svg",
                ".gif",
                ".woff",
                ".pdf",
                ".zip",
                ".ico",
            ]
    
        self.block_urls(
            images_patterns
        )
        
    def __eq__(self, other: Tab):
        try:
            return other.target == self.target
        except (AttributeError, TypeError):
            return False

    # def __getattr__(self, item):
    #     try:
    #         return getattr(self._target, item)
    #     except AttributeError:
    #         raise AttributeError(
    #             f'"{self.__class__.__name__}" has no attribute "%s"' % item
    #         )
    def __repr__(self):
        if self.target.url:
            extra = f"[url: {self.target.url}]"
            s = f"<{type(self).__name__} [{self.target.target_id}] [{self.target.type_}] {extra}>"
        else: 
            s = f"<{type(self).__name__} [{self.target.target_id}] [{self.target.type_}]>"
        return s

class Frame(cdp.page.Frame):
    execution_contexts: typing.Dict[str, ExecutionContext] = {}

    def __init__(self, id_: cdp.page.FrameId, **kw):
        none_gen = repeat_none
        param_names = util.get_all_param_names(self.__class__)
        param_names.remove("execution_contexts")
        for k in kw:
            param_names.remove(k)
        params = dict(zip(param_names, none_gen))
        params.update({"id_": id_, **kw})
        super().__init__(**params)
def repeat_none():
    while True:
        yield None

class ExecutionContext(dict):
    id: cdp.runtime.ExecutionContextId
    frame_id: str
    unique_id: str
    _tab: Tab

    def __init__(self, *a, **kw):
        super().__init__()
        super().__setattr__("__dict__", self)
        d: typing.Dict[str, Union[Tab, str]] = dict(*a, **kw)
        self._tab: Tab = d.pop("tab", None)
        self.__dict__.update(d)

    def __repr__(self):
        return "<ExecutionContext (\n{}\n)".format(
            "".join(f"\t{k} = {v}\n" for k, v in super().items() if k not in ("_tab"))
        )

    def evaluate(
        self,
        expression,
        allow_unsafe_eval_blocked_by_csp: bool = True,
        await_promises: bool = False,
        generate_preview: bool = False,
    ):
        try:
            raw = self._tab.send(
                cdp.runtime.evaluate(
                    expression=expression,
                    context_id=self.get("id_"),
                    generate_preview=generate_preview,
                    return_by_value=False,
                    allow_unsafe_eval_blocked_by_csp=allow_unsafe_eval_blocked_by_csp,
                    await_promise=await_promises,
                )
            )
            if raw:
                remote_object, errors = raw
                if errors:
                    raise ChromeException(errors)

                if remote_object:
                    return remote_object

                # else:
                #     return remote_object, errors

        except:  # noqa
            raise

