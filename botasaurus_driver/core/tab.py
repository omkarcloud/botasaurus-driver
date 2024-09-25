from __future__ import annotations
import json
import time
import typing
from datetime import datetime
from typing import List, Union, Optional

from ..exceptions import handle_exception, ReferenceError, SyntaxError, ElementWithSelectorNotFoundException, DriverException, JavascriptException, ChromeException, InvalidFilenameException, JavascriptSyntaxException, ScreenshotException
from ..driver_utils import create_screenshot_filename, get_download_directory, get_download_filename

from . import element
from . import util
from .config import PathLike
from .connection import Connection
from .. import cdp


bannedtextsearchresults = set(["title","meta", "script", "link", "style", "head"])
def isbanned(node):
        return node.node_name.lower() in bannedtextsearchresults

def issametype(node, type):
        return node.node_name.lower() ==type
def append_safe(results, elem, text, exact_match):
            if exact_match:
                if text == elem.text:
                    results.append(elem)
            else:
                results.append(elem)
              
def make_core_string(SCRIPT,args ):
            expression = r"const args = JSON.parse('ARGS'); SCRIPT".replace("SCRIPT", SCRIPT)
            if args is not None:
                expression = expression.replace("ARGS",  json.dumps(args).replace(r'\"', r'\\"'))
            else:
                expression = expression.replace("const args = JSON.parse('ARGS'); ", "")
            return expression                
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
        browser= None,
        **kwargs,
    ):
        super().__init__(websocket_url, target, **kwargs)
        self.browser = browser
        self._dom = None
        self._window_id = None
        self.is_closed = False


    def _run(self, coro):
        return coro

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
        now = time.time()

        item = self.find_element_by_text(
            text, best_match, return_enclosing_element, type=type, exact_match=exact_match
        )
        if timeout:
            while not item:
                item = self.find_element_by_text(
                    text, best_match, return_enclosing_element, type=type, exact_match=exact_match
                )
                if time.time() - now > timeout:
                    return None
                self.sleep(0.5)
        return item

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
        now = time.time()

        item = self.query_selector(selector, _node)
        if timeout:
            while not item:
                item = self.query_selector(selector, _node)
                if time.time() - now > timeout:
                    return None
                self.sleep(0.5)
        return item

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
        doc: cdp.dom.Node = self.send(cdp.dom.get_document(-1, True))
        # print(self.send(cdp.dom.get_node_for_location(x=x, y=y, include_user_agent_shadow_dom=False)))
        try:
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
        now = time.time()
        results = self.perform_get_element_at_point(x,y)
        if timeout:
            while not results:
                results = self.perform_get_element_at_point(x,y)
                if time.time() - now > timeout:
                    return results
                self.sleep(0.5)
        return results

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
        now = time.time()

        results = self.find_elements_by_text(text, type=type, exact_match=exact_match)
        if timeout:
            while not results:
                results = self.find_elements_by_text(text, type=type, exact_match=exact_match)
                if time.time() - now > timeout:
                    return []
                self.sleep(0.5)
        return results

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

        now = time.time()
        results = self.query_selector_all(selector, _node)
        if timeout:
            while not results:
                results = self.query_selector_all(selector, _node)
                if time.time() - now > timeout:
                    return results
                self.sleep(0.5)
        if not results:
            return []
        results = [item for item in results if item.node.node_name.lower() == node_name.lower()] if node_name else results

        return results

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

        now = time.time()
        results = self.query_selector_count(selector, _node)
        if timeout:
            while not results:
                results = self.query_selector_count(selector, _node)
                if time.time() - now > timeout:
                    return 0
                self.sleep(0.5)
        if not results:
            return 0
        return results

    def query_selector_all(
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
                    if getattr(_node, "__last", None):
                        del _node.__last
                        return []
                    # if supplied node is not found, the dom has changed since acquiring the element
                    # therefore we need to update our passed node and try again
                    _node.update()
                    _node.__last = (
                        True  # make sure this isn't turned into infinite loop
                    )
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
                    if getattr(_node, "__last", None):
                        del _node.__last
                        return 0
                    # if supplied node is not found, the dom has changed since acquiring the element
                    # therefore we need to update our passed node and try again
                    _node.update()
                    _node.__last = (
                        True  # make sure this isn't turned into infinite loop
                    )
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
                    if getattr(_node, "__last", None):
                        del _node.__last
                        return None
                    # if supplied node is not found, the dom has changed since acquiring the element
                    # therefore we need to update our passed node and try again
                    _node.update()
                    _node.__last = (
                        True  # make sure this isn't turned into infinite loop
                    )
                    return self.query_selector(selector, _node)
            else:
                self.send(cdp.dom.disable())
                if is_no_node:
                    # simply means that doc was destroyed in navigation
                    return None
                raise
        if not node_id:
            return
        node = util.filter_recurse(doc, lambda n: n.node_id == node_id)
        if not node:
            return
        return element.create(node, self, doc)

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

        # since we already fetched the entire doc, including shadow and frames
        # let's also search through the iframes
        # iframes = util.filter_recurse_all(doc, lambda node: node.node_name == "IFRAME")
        # if iframes:
            # iframes_elems = [
            #     element.create(iframe, self, iframe.content_document)
            #     for iframe in iframes
            # ]
            # for iframe_elem in iframes_elems:
            #     if iframe_elem.content_document:
            #         iframe_text_nodes = util.filter_recurse_all(
            #             iframe_elem,
            #             lambda node: node.node_type == 3  # noqa
            #             and text.lower() in node.node_value.lower(),
            #         )
            #         if iframe_text_nodes:
            #             iframe_text_elems = [
            #                 element.create(text_node, self, iframe_elem.tree)
            #                 for text_node in iframe_text_nodes
            #             ]
            #             results.extend(
                        #     text_node.parent for text_node in iframe_text_elems
                        # )
        self.send(cdp.dom.disable())
        return results or []

    def run_cdp_command(self, command):
        return self.send(command)

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
            node_ids = []
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

        # since we already fetched the entire doc, including shadow and frames
        # let's also search through the iframes
        # iframes = util.filter_recurse_all(doc, lambda node: node.node_name == "IFRAME")
        # if iframes:
        #     iframes_elems = [
        #         element.create(iframe, self, iframe.content_document)
        #         for iframe in iframes
        #     ]
        #     for iframe_elem in iframes_elems:
                # iframe_text_nodes = util.filter_recurse_all(
                #     iframe_elem,
                #     lambda node: node.node_type == 3  # noqa
                #     and text.lower() in node.node_value.lower(),
                # )
                # if iframe_text_nodes:
                #     iframe_text_elems = [
                #         element.create(text_node, self, iframe_elem.tree)
                #         for text_node in iframe_text_nodes
                #     ]
                #     results.extend(text_node.parent for text_node in iframe_text_elems)
        try:
            if not results:
                return
                # naively just return the first result
            for elem in results:
                if elem:
                    return elem
        finally:
            self.send(cdp.dom.disable())

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
                           ___dumpY( %s )
                   """
            % obj_name
        )
        js_code_b = (
            """
            ((obj, visited = new WeakSet()) => {
                 if (visited.has(obj)) {
                     return {}
                 }
                 visited.add(obj)
                 var result = {}, _tmp;
                 for (var i in obj) {
                         try {
                             if (i === 'enabledPlugin' || typeof obj[i] === 'function') {
                                 continue;
                             } else if (typeof obj[i] === 'object') {
                                 _tmp = recurse(obj[i], visited);
                                 if (Object.keys(_tmp).length) {
                                     result[i] = _tmp;
                                 }
                             } else {
                                 result[i] = obj[i];
                             }
                         } catch (error) {
                             // console.error('Error:', error);
                         }
                     }
                return result;
            })(%s)
        """
            % obj_name
        )

        # we're purposely not calling self.evaluate here to prevent infinite loop on certain expressions

        remote_object, exception_details = self.send(
            cdp.runtime.evaluate(
                js_code_a,
                await_promise=True,
                return_by_value=return_by_value,
                allow_unsafe_eval_blocked_by_csp=True,
            )
        )
        if exception_details:

            # try second variant

            remote_object, exception_details = self.send(
                cdp.runtime.evaluate(
                    js_code_b,
                    await_promise=True,
                    return_by_value=return_by_value,
                    allow_unsafe_eval_blocked_by_csp=True,
                )
            )

        if exception_details:
            raise JavascriptException(exception_details)
        if return_by_value:
            if remote_object.value:
                return remote_object.value
        else:
            return remote_object, exception_details

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


    def download_file(self, url: str, filename: Optional[PathLike] = None):
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
      
        body = (self.query_selector_all("body"))[0]
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

    def __eq__(self, other: Tab):
        try:
            return other.target == self.target
        except (AttributeError, TypeError):
            return False

    def __getattr__(self, item):
        try:
            return getattr(self._target, item)
        except AttributeError:
            raise AttributeError(
                f'"{self.__class__.__name__}" has no attribute "%s"' % item
            )

    def __repr__(self):
        extra = ""
        if self.target.url:
            extra = f"[url: {self.target.url}]"
            s = f"<{type(self).__name__} [{self.target_id}] [{self.type_}] {extra}>"
        else: 
            s = f"<{type(self).__name__} [{self.target_id}] [{self.type_}]>"
        return s
