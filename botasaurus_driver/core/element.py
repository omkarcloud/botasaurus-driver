from __future__ import annotations

import json
import os
import time
import typing

from ..exceptions import ChromeException, DetachedElementException, ElementInitializationException, ElementPositionException, ElementPositionNotFoundException, ElementScreenshotException, ElementWithSelectorNotFoundException, InvalidFilenameException
from ..driver_utils import create_screenshot_filename, get_download_directory, get_download_filename

from . import util
from ._contradict import ContraDict
from .config import PathLike
from .. import cdp

if typing.TYPE_CHECKING:
    from .tab import Tab

def make_core_string(SCRIPT,args ):
            expression = r"const args = JSON.parse('ARGS'); const resp = (SCRIPT)(element);".replace("SCRIPT", SCRIPT)
            if args is not None:
                expression = expression.replace("ARGS",  json.dumps(args).replace(r'\"', r'\\"'))
            else:
                expression = expression.replace("const args = JSON.parse('ARGS'); ", "")
            return expression
def create(node: cdp.dom.Node, tab: Tab, tree: typing.Optional[cdp.dom.Node] = None):
    """
    factory for Elements
    this is used with Tab.query_selector(_all), since we already have the tree,
    we don't need to fetch it for every single element.

    :param node: cdp dom node representation
    :type node: cdp.dom.Node
    :param tab: the target object to which this element belongs
    :type tab: Tab
    :param tree: [Optional] the full node tree to which <node> belongs, enhances performance.
                when not provided, you need to call `elem.update()` before using .children / .parent
    :type tree:
    """

    elem = Element(node, tab, tree)

    return elem

class Element:
    def __init__(self, node: cdp.dom.Node, tab: Tab, tree: cdp.dom.Node = None):
        """
        Represents an (HTML) DOM Element

        :param node: cdp dom node representation
        :type node: cdp.dom.Node
        :param tab: the target object to which this element belongs
        :type tab: Tab
        """
        if not node:
            raise ElementInitializationException("Node cannot be None")
        self._tab = tab
        # if node.node_name == 'IFRAME':
        #     self._node = node.content_document
        # else:
        self._node = node
        self._tree = tree
        self._parent = None
        self._remote_object = None
        self._attrs = ContraDict(silent=True)
        self._make_attrs()

    @property
    def tag(self):
        return self.node.node_name.lower()

    @property
    def tag_name(self):
        return self.tag

    @property
    def node_id(self):
        return self.node.node_id

    @property
    def backend_node_id(self):
        return self.node.backend_node_id

    @property
    def node_type(self):
        return self.node.node_type

    @property
    def node_name(self):
        return self.node.node_name

    @property
    def local_name(self):
        return self.node.local_name

    @property
    def node_value(self):
        return self.node.node_value

    @property
    def parent_id(self):
        return self.node.parent_id

    @property
    def child_node_count(self):
        return self.node.child_node_count

    @property
    def attributes(self):
        return self.node.attributes

    @property
    def document_url(self):
        return self.node.document_url

    @property
    def base_url(self):
        return self.node.base_url

    @property
    def public_id(self):
        return self.node.public_id

    @property
    def system_id(self):
        return self.node.system_id

    @property
    def internal_subset(self):
        return self.node.internal_subset

    @property
    def xml_version(self):
        return self.node.xml_version

    @property
    def value(self):
        return self.node.value

    @property
    def pseudo_type(self):
        return self.node.pseudo_type

    @property
    def pseudo_identifier(self):
        return self.node.pseudo_identifier

    @property
    def shadow_root_type(self):
        return self.node.shadow_root_type

    @property
    def frame_id(self):
        return self.node.frame_id

    @property
    def content_document(self):
        return self.node.content_document

    @property
    def shadow_roots(self):
        return self.node.shadow_roots

    @property
    def template_content(self):
        return self.node.template_content

    @property
    def pseudo_elements(self):
        return self.node.pseudo_elements

    @property
    def imported_document(self):
        return self.node.imported_document

    @property
    def distributed_nodes(self):
        return self.node.distributed_nodes

    @property
    def is_svg(self):
        return self.node.is_svg

    @property
    def compatibility_mode(self):
        return self.node.compatibility_mode

    @property
    def assigned_slot(self):
        return self.node.assigned_slot

    @property
    def tab(self):
        return self._tab

    def __getattr__(self, item):
        # if attribute is not found on the element python object
        # check if it may be present in the element attributes (eg, href=, src=, alt=)
        # returns None when attribute is not found
        # instead of raising AttributeError
        x = getattr(self.attrs, item, None)
        if x:
            return x

    #     x = getattr(self.node, item, None)
    #
    #     return x

    def __setattr__(self, key, value):
        if key[0] != "_":
            if key[1:] not in vars(self).keys():
                # we probably deal with an attribute of
                # the html element, so forward it
                self.attrs.__setattr__(key, value)
                return
        # we probably deal with an attribute of
        # the python object
        super().__setattr__(key, value)

    def __setitem__(self, key, value):
        if key[0] != "_":
            if key[1:] not in vars(self).keys():
                # we probably deal with an attribute of
                # the html element, so forward it
                self.attrs[key] = value

    def __getitem__(self, item):
        # we probably deal with an attribute of
        # the html element, so forward it
        return self.attrs.get(item, None)

    def update(self, _node=None):
        """
        updates element to retrieve more properties. for example this enables
        :py:obj:`~children` and :py:obj:`~parent` attributes.

        also resolves js opbject which is stored object in :py:obj:`~remote_object`

        usually you will get element nodes by the usage of

        :py:meth:`Tab.query_selector_all()`

        :py:meth:`Tab.find_elements_by_text()`

        those elements are already updated and you can browse through children directly.

        The reason for a seperate call instead of doing it at initialization,
        is because when you are retrieving 100+ elements this becomes quite expensive.

        therefore, it is not advised to call this method on a bunch of blocks (100+) at the same time.

        :return:
        :rtype:
        """
        if _node:
            doc = _node
            # self._node = _node
            # self._children.clear()
            self._parent = None
        else:
            doc =  self._tab.send(cdp.dom.get_document(-1, True))
            self._parent = None
        # if self.node_name != "IFRAME":
        updated_node = util.filter_recurse(
            doc, lambda n: n.backend_node_id == self._node.backend_node_id
        )
        if updated_node:
            self._node = updated_node
        self._tree = doc

        self._remote_object =  self._tab.send(
            cdp.dom.resolve_node(backend_node_id=self._node.backend_node_id)
        )
        self.attrs.clear()
        self._make_attrs()
        if self.node_name != "IFRAME":
            parent_node = util.filter_recurse(
                doc, lambda n: n.node_id == self.node.parent_id
            )
            if not parent_node:
                # could happen if node is for example <html>
                return self
            self._parent = create(parent_node, tab=self._tab, tree=self._tree)
        return self

    @property
    def node(self):
        return self._node

    @property
    def tree(self) -> cdp.dom.Node:
        return self._tree
        # raise RuntimeError("you should first call  `await update()` on this object to populate it's tree")

    @tree.setter
    def tree(self, tree: cdp.dom.Node):
        self._tree = tree

    @property
    def attrs(self):
        """
        attributes are stored here, however, you can set them directly on the element object as well.
        :return:
        :rtype:
        """
        return self._attrs

    @property
    def parent(self) -> typing.Union[Element, None]:
        """
        get the parent element (node) of current element(node)
        :return:
        :rtype:
        """
        if not self.tree:
            raise ElementInitializationException("Could not get parent since the element has no tree set")
        parent_node = util.filter_recurse(
            self.tree, lambda n: n.node_id == self.parent_id
        )
        if not parent_node:
            return None
        parent_element = create(parent_node, tab=self._tab, tree=self.tree)
        return parent_element

    @property
    def children(self) -> typing.Union[typing.List[Element], str]:
        """
        returns the elements' children. those children also have a children property
        so you can browse through the entire tree as well.
        :return:
        :rtype:
        """
        _children = []
        if self._node.node_name == "IFRAME":
            # iframes are not exact the same as other nodes
            # the children of iframes are found under
            # the .content_document property, which is of more
            # use than the node itself
            frame = self._node.content_document
            if not frame.child_node_count:
                return []
            for child in frame.children:
                child_elem = create(child, self._tab, frame)
                if child_elem:
                    _children.append(child_elem)
            # self._node = frame
            return _children
        elif not self.node.child_node_count:
            return []
        if self.node.children:
            for child in self.node.children:
                child_elem = create(child, self._tab, self.tree)
                if child_elem:
                    _children.append(child_elem)
        return _children

    @property
    def remote_object(self) -> cdp.runtime.RemoteObject:
        return self._remote_object

    @property
    def object_id(self) -> cdp.runtime.RemoteObjectId:
        try:
            return self.remote_object.object_id
        except AttributeError:
            pass

    def mouse_move(self):
        """moves mouse (not click), to element position. when an element has an
        hover/mouseover effect, this would trigger it"""
        center = self.get_position().center
        
        x = center[0] -4
        y = center[1]- 4
        self._tab.send(
            cdp.input_.dispatch_mouse_event("mouseMoved", x=x, y=y)
        )
        # self._tab.sleep(0.07)
        # self._tab.send(
        #     cdp.input_.dispatch_mouse_event("mouseReleased", x=center[0]-4, y=center[1]-4)
        # )
    def humane_click(self):
        """
        Click the element.

        :return:
        :rtype:
        """
        self.raise_if_disconnected()

        center = self.get_position().center
        # a bit off for better humaness
        x = center[0] - 4
        y = center[1] - 3
        self._tab.send(
            cdp.input_.dispatch_mouse_event("mouseMoved", x=x, y=y)
        )
        time.sleep(0.07)
        self._tab.send(
           cdp.input_.dispatch_mouse_event(
            "mousePressed",
            x=x,
            y=y,
            button=cdp.input_.MouseButton.LEFT,
            click_count=1
        )
        )
        time.sleep(0.09)
        self._tab.send (cdp.input_.dispatch_mouse_event(
            "mouseReleased",
            x=x,
            y=y,
            button=cdp.input_.MouseButton.LEFT,
            click_count=1
        ))
    def press_and_hold(self, wait):
        """
        Click the element.

        :return:
        :rtype:
        """
        self.raise_if_disconnected()

        center = self.get_position().center
        # a bit off for better humaness
        x = center[0] - 33
        y = center[1] - 20
        self._tab.send(
            cdp.input_.dispatch_mouse_event("mouseMoved", x=x, y=y)
        )
        time.sleep(0.07)
        self._tab.send(
           cdp.input_.dispatch_mouse_event(
            "mousePressed",
            x=x,
            y=y,
            button=cdp.input_.MouseButton.LEFT,
            click_count=1
        )
        )
        time.sleep(wait)
        self._tab.send (cdp.input_.dispatch_mouse_event(
            "mouseReleased",
            x=x,
            y=y,
            button=cdp.input_.MouseButton.LEFT,
            click_count=1
        ))        

    def click(self):
        """
        Click the element.

        :return:
        :rtype:
        """
        self.raise_if_disconnected()
        self._remote_object = self._tab.send(
            cdp.dom.resolve_node(backend_node_id=self.backend_node_id)
        )
        arguments = [cdp.runtime.CallArgument(object_id=self._remote_object.object_id)]
        self.flash(0.25)
        self._tab.send(
            cdp.runtime.call_function_on(
                "(el) => el.click()",
                object_id=self._remote_object.object_id,
                arguments=arguments,
                await_promise=True,
                user_gesture=True,
                return_by_value=True,
            )
        )

    def check_element(self):
        is_checked = self.apply("(el) => el.checked")
        if not is_checked:
            self.click()
            self.update()

    def uncheck_element(self):
        is_checked = self.apply("(el) => el.checked")
        if is_checked:
            self.click()
            self.update()
            
    def wait_for(self, selector="", text="", timeout=10):
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
        self.raise_if_disconnected()

        now = time.time()
        if selector:
            item = self.query_selector(selector)
            while not item:
                item = self.query_selector(selector)
                if time.time() - now > timeout:
                    # Raise Exception if it is not found till this time
                    raise ElementWithSelectorNotFoundException(selector)
                time.sleep(0.5)
            return item

    def __call__(self, js_method):
        """
        calling the element object will call a js method on the object
        eg, element.play() in case of a video element, it will call .play()
        :param js_method:
        :type js_method:
        :return:
        :rtype:
        """
        return self.apply(f"(e) => e['{js_method}']()")

    def apply(self, js_function, args=None,return_by_value=True):
        """
        apply javascript to this element. the given js_function string should accept the js element as parameter,
        and can be an arrow function, or function declaration.
        eg:
            - '(elem) => { elem.value = "blabla"; consolelog(elem); alert(JSON.stringify(elem); } '
            - 'elem => elem.play()'
            - 'function myFunction(elem) { alert(elem) }'

        :param js_function: the js function definition which received this element.
        :type js_function: str
        :param return_by_value:
        :type return_by_value:
        :return:
        :rtype:
        """
        core = make_core_string(js_function, args)
        js_function = r"""function (element) {
    CORE
    return JSON.stringify({ "x": resp });
    }""".replace("CORE", core)

        try:

            self._remote_object = self._tab.send(
                cdp.dom.resolve_node(backend_node_id=self.backend_node_id)
            )
            result = self._tab.send(
                cdp.runtime.call_function_on(
                    js_function,
                    object_id=self._remote_object.object_id,
                    arguments=[
                        cdp.runtime.CallArgument(
                            object_id=self._remote_object.object_id
                        )
                    ],
                    return_by_value=True,
                    user_gesture=True,
                )
            )

            if result and result[0]:
                if return_by_value:
                    return json.loads(util.get_remote_object_value(result[0], core)).get("x")
                return json.loads(result[0]).get("x")
            elif result[1]:
                return json.loads(result[1]).get("x")

        except Exception as e:
          if self.is_disconnected_error(e):
              raise DetachedElementException()
          raise
    def get_position(self, abs=False):
        self.raise_if_disconnected()

        if not self.parent or not self.object_id:
            self._remote_object = self._tab.send(
                cdp.dom.resolve_node(backend_node_id=self.backend_node_id)
            )
            # self.update()
        try:
            quads = self.tab.send(
                cdp.dom.get_content_quads(object_id=self.remote_object.object_id)
            )
            if not quads:
                raise ElementPositionNotFoundException(self)
            pos = Position(quads[0])
            if abs:
                scroll_y = self.tab.evaluate("window.scrollY")
                scroll_x = self.tab.evaluate("window.scrollX")
                abs_x = pos.left + scroll_x + (pos.width / 2)
                abs_y = pos.top + scroll_y + (pos.height / 2)
                pos.abs_x = abs_x
                pos.abs_y = abs_y
            return pos
        except IndexError:
            pass    
    def mouse_click(
        self,
        button: str = "left",
        buttons: typing.Optional[int] = 1,
        modifiers: typing.Optional[int] = 0,
        _until_event: typing.Optional[type] = None,
    ):
        """native click (on element) . note: this likely does not work atm, use click() instead

        :param button: str (default = "left")
        :param buttons: which button (default 1 = left)
        :param modifiers: *(Optional)* Bit field representing pressed modifier keys.
                Alt=1, Ctrl=2, Meta/Command=4, Shift=8 (default: 0).
        :param _until_event: internal. event to wait for before returning
        :return:

        """
        self.raise_if_disconnected()

        try:
            center = self.get_position().center
        except AttributeError:
            return
        if not center:
            return

        self._tab.send(
            cdp.input_.dispatch_mouse_event(
                "mousePressed",
                x=center[0],
                y=center[1],
                modifiers=modifiers,
                button=cdp.input_.MouseButton(button),
                buttons=buttons,
                click_count=1,
            )
        )
        self._tab.send(
            cdp.input_.dispatch_mouse_event(
                "mouseReleased",
                x=center[0],
                y=center[1],
                modifiers=modifiers,
                button=cdp.input_.MouseButton(button),
                buttons=buttons,
                click_count=1,
            )
        )
        try:
            self.flash()
        except:  # noqa
            pass

    def scroll_into_view(self):
        """scrolls element into view"""
        self.raise_if_disconnected()

        try:
            self.tab.send(
                cdp.dom.scroll_into_view_if_needed(backend_node_id=self.backend_node_id)
            )
        except Exception as e:
            return

    def clear_input(self, _until_event: type = None):
        """clears an input field"""
        self.raise_if_disconnected()
        self.apply('function (element) { element.value = "" } ')
        self.update()

    def raise_if_disconnected(self):
        response = self.is_disconnected()
        if response:
            raise DetachedElementException()

    def is_disconnected(self):        
        try:
          return self.apply('(el)=>!el.isConnected')
        except Exception as e:
          if self.is_disconnected_error(e):
              return True
          raise 

    def is_disconnected_error(self, e):
        msg = str(e).lower()
        if "node with given id" in msg or "cannot find context with" in msg :
            return True
        return False
        

    def send_keys(self, text: str):
        """
        send text to an input field, or any other html element.

        hint, if you ever get stuck where using py:meth:`~click`
        does not work, sending the keystroke \\n or \\r\\n or a spacebar work wonders!

        :param text: text to send
        :return: None
        """
        self.raise_if_disconnected()
        self.apply("(elem) => elem.focus()")
        for char in list(text):
            self._tab.send(cdp.input_.dispatch_key_event("char", text=char))

        self.update()

    def send_file(self, *file_paths):
        """
        some form input require a file (upload), a full path needs to be provided.
        this method sends 1 or more file(s) to the input field.

        needles to say, but make sure the field accepts multiple files if you want to send more files.
        otherwise the browser might crash.

        example :
        `fileinputElement.send_file('c:/temp/image.png', 'c:/users/myuser/lol.gif')`

        """
        self.raise_if_disconnected()

        self._tab.send(
            cdp.dom.set_file_input_files(
                files=file_paths,
                backend_node_id=self.backend_node_id,
                object_id=self.object_id,
            )
        )

    def get_html(self):
        self.raise_if_disconnected()

        return self._tab.send(
            cdp.dom.get_outer_html(backend_node_id=self.backend_node_id)
        )
    @property
    def text(self):
        """
        gets the text contents of this element
        note: this includes text in the form of script content, as those are also just 'text nodes'

        :return:
        :rtype:
        """
        text_node = util.filter_recurse(self.node, lambda n: n.node_type == 3)
        if text_node:
            return text_node.node_value
        return ""

    @property
    def text_all(self):
        """
        gets the text contents of this element, and it's children in a concatenated string
        note: this includes text in the form of script content, as those are also just 'text nodes'
        :return:
        :rtype:
        """
        text_nodes = util.filter_recurse_all(self.node, lambda n: n.node_type == 3)
        return " ".join([n.node_value for n in text_nodes])

    def query_selector_all(self, selector, timeout, node_name=None):
        """
        like js querySelectorAll()
        """
        self.raise_if_disconnected()

        self.update()
        # return self.tab.query_selector_all(selector, _node=self)
        return self.tab.select_all(selector, timeout, node_name=node_name, _node=self)

    def query_selector(self, selector, timeout):
        """
        like js querySelector()
        """
        self.raise_if_disconnected()

        self.update()
        return self.tab.select(selector, timeout, self)

    def save_screenshot(
        self,
        filename=None,
        format="png",
        scale=1,
    ):
        """
        Saves a screenshot of this element (only)
        This is not the same as :py:obj:`Tab.save_screenshot`, which saves a "regular" screenshot

        When the element is hidden, or has no size, or is otherwise not capturable, a RuntimeError is raised

        :param filename: uses this as the save path
        :type filename: PathLike
        :param format: jpeg or png (defaults to jpeg)
        :type format: str
        :param scale: the scale of the screenshot, eg: 1 = size as is, 2 = double, 0.5 is half
        :return: the path/filename of saved screenshot
        :rtype: str
        """

        import base64
        if not filename:
            raise InvalidFilenameException(filename)

        filename, relative_path = create_screenshot_filename(filename)

        self.raise_if_disconnected()

        pos = self.get_position()
        if not pos:
            raise ElementPositionException()
        viewport = pos.to_viewport(scale)
        self.tab.sleep()

        path = filename

        if format.lower() in ["jpg", "jpeg"]:
            ext = ".jpg"
            format = "jpeg"

        elif format.lower() in ["png"]:
            ext = ".png"
            format = "png"

        data = self._tab.send(
            cdp.page.capture_screenshot(
                format, clip=viewport, capture_beyond_viewport=True
            )
        )
        if not data:
            raise ElementScreenshotException()

        data_bytes = base64.b64decode(data)
        with open(path, "wb") as file:
            file.write(data_bytes)
        print(f"View screenshot at {relative_path}")
        return str(path)

    def flash(self, duration=0.5):
        """
        displays for a short time a red dot on the element (only if the element itself is visible)

        :param coords: x,y
        :type coords: x,y
        :param duration: seconds (default 0.5)
        :type duration:
        :return:
        :rtype:
        """
        
        import secrets
        self.raise_if_disconnected()

        if not self.remote_object:
            try:
                self._remote_object = self.tab.send(
                    cdp.dom.resolve_node(backend_node_id=self.backend_node_id)
                )
            except ChromeException:
                return
        try:
            pos = self.get_position()

        except (Exception,):
            return

        style = (
            "position:absolute;z-index:99999999;padding:0;margin:0;"
            "left:{:.1f}px; top: {:.1f}px;"
            "opacity:1;"
            "width:16px;height:16px;border-radius:50%;background:red;"
            "animation:show-pointer-ani {:.2f}s ease 1;"
        ).format(
            pos.center[0] - 8,  # -8 to account for drawn circle itself (w,h)
            pos.center[1] - 8,
            duration,
        )
        script = (
            """
            (targetElement) => {{
                var css = document.styleSheets[0];
                for( let css of [...document.styleSheets]) {{
                    try {{
                        css.insertRule(`
                        @keyframes show-pointer-ani {{
                            0% {{ opacity: 1; transform: scale(2, 2);}}
                            25% {{ transform: scale(5,5) }}
                            50% {{ transform: scale(3, 3);}}
                            75%: {{ transform: scale(2,2) }}
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
            }}
            """.format(
                style,
                secrets.token_hex(8),
                int(duration * 1000),
            )
            .replace("  ", "")
            .replace("\n", "")
        )

        arguments = [cdp.runtime.CallArgument(object_id=self._remote_object.object_id)]
        self._tab.send(
            cdp.runtime.call_function_on(
                script,
                object_id=self._remote_object.object_id,
                arguments=arguments,
                await_promise=True,
                user_gesture=True,
            )
        )
    def download_video(self, filename, duration: typing.Optional[typing.Union[int, float]] = None):
        """
        experimental option.
        :param filename: the desired filename
        :param folder: the download folder path
        :param duration: record for this many seconds and then download on html5 video nodes, you can call this method to start recording of the video. when any of the follow happens:
        - video ends
        - calling videoelement('pause')
        - video stops the video recorded will be downloaded.
        """
        self.raise_if_disconnected()
        download_dir = get_download_directory()
        self._tab.send(
            cdp.browser.set_download_behavior(
                "allow", download_path=download_dir
            )
        )
        video_download_path, relative_path = get_download_filename(filename)
        self.video_download_path = video_download_path
        self.apply('(vid) => vid.pause()')
        self.apply(
            """
            function extractVid(vid) {
                var duration = {duration:.1f};
                var stream = vid.captureStream();
                var mr = new MediaRecorder(stream, {{audio:true, video:true}})
                mr.ondataavailable = function(e) {
                    var blob = e.data;
                    f = new File([blob], {{name: {filename}, type:'octet/stream'}});
                    var objectUrl = URL.createObjectURL(f);
                    var link = document.createElement('a');
                    link.setAttribute('href', objectUrl)
                    link.setAttribute('download', {filename})
                    link.style.display = 'none'
                    document.body.appendChild(link)
                    link.click()
                    vid['_recording'] = false
                    document.body.removeChild(link)
                }
                mr.start()
                vid.addEventListener('ended' , (e) => mr.stop())
                vid.addEventListener('pause' , (e) => mr.stop())
                vid.addEventListener('abort', (e) => mr.stop())
                if ( duration ) {
                    setTimeout(() => {
                        vid.pause();
                        vid.play()
                    }, duration);
                }
                vid['_recording'] = true ;
            }
            """.format(
                filename=f'"{filename}"' if filename else 'document.title + ".mp4"',
                duration=int(duration * 1000) if duration else 0,
            )
        )
        self.apply('(vid) => vid.play()')
        self._tab
        return relative_path

    def is_video_downloaded(self):
        isrecording = self.apply('(vid) => vid["_recording"]')
        if isrecording is None:
            return False
        return not isrecording and self.video_download_path and os.path.exists(self.video_download_path)
    def _make_attrs(self):
        sav = None
        if self.node.attributes:
            for i, a in enumerate(self.node.attributes):
                if i == 0 or i % 2 == 0:
                    # if a == "class":
                    #     a = "class_"
                    sav = a
                else:
                    if sav:
                        self.attrs[sav] = a

    def __eq__(self, other: Element) -> bool:
        # if other.__dict__.values() == self.__dict__.values():
        #     return True
        if other.backend_node_id and self.backend_node_id:
            return other.backend_node_id == self.backend_node_id

        return False

    def __repr__(self):
        tag_name = self.node.node_name.lower()
        content = ""

        # collect all text from this leaf
        if self.child_node_count:
            if self.child_node_count == 1:
                if self.children:
                    content += str(self.children[0])

            elif self.child_node_count > 1:
                if self.children:
                    for child in self.children:
                        content += str(child)

        if self.node.node_type == 3:  # we could be a text node ourselves
            content += self.node_value

            # return text only, no tag names
            # this makes it look most natural, and compatible with other hml libs

            return content

        attrs = " ".join(
            [f'{k if k != "class_" else "class"}="{v}"' for k, v in self.attrs.items()]
        )
        s = f"<{tag_name} {attrs}>{content}</{tag_name}>"
        return s

class Position(cdp.dom.Quad):
    """helper class for element positioning"""

    def __init__(self, points):
        super().__init__(points)
        (
            self.left,
            self.top,
            self.right,
            self.top,
            self.right,
            self.bottom,
            self.left,
            self.bottom,
        ) = points
        self.abs_x: float = 0
        self.abs_y: float = 0
        self.x = self.left
        self.y = self.top
        self.height, self.width = (self.bottom - self.top, self.right - self.left)
        self.center = (
            self.left + (self.width / 2),
            self.top + (self.height / 2),
        )

    def to_viewport(self, scale=1):
        return cdp.page.Viewport(
            x=self.x, y=self.y, width=self.width, height=self.height, scale=scale
        )

    def __repr__(self):
        return f"<Position(x={self.left}, y={self.top}, width={self.width}, height={self.height})>"
