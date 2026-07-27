import json
from random import uniform
from datetime import datetime
from time import sleep
import time
import os
from typing import Callable, Optional, Union, List, Any
from .exceptions import ChromeException, DriverException, UnavailableMethodError

from .core.config import Config
from .tiny_profile import load_cookies, save_cookies
from . import cdp
from .core._contradict import ContraDict
from .core.util import wait_for_result


from .beep_utils import beep_input
from .driver_utils import (
    convert_to_absolute_path,
    create_video_filename,
    ensure_supports_file_upload,
    ensure_supports_multiple_upload,
    perform_accept_google_cookies_action,
    sleep_for_n_seconds,
    sleep_forever,
    with_human_mode,
)
from .exceptions import (
    CheckboxElementForLabelNotFoundException,
    DetachedElementException,
    ElementWithTextNotFoundException,
    InputElementForLabelNotFoundException,
    InvalidProfileException,
    NoProfileException,
    PageNotFoundException,
)
from .local_storage_driver import LocalStorage
from .opponent import Opponent
from .solve_cloudflare_captcha import bypass_if_detected, wait_till_document_is_ready
from .core.browser import Browser
from .core.util import start
from .core.tab import Tab, make_iife
from .core.element import DictPosition, Element as CoreElement, calc_center



def read_file(path):
    with open(path, 'r', encoding="utf-8") as fp:
        content = fp.read()
        return content
    
def load_script_if_js_file(script):
    if script is None:
        return None
    elif script.endswith(".js"):
        return read_file(script)
    else:
        return script
    
class Wait:
    SHORT = 4
    LONG = 8
    VERY_LONG = 16

    
def make_element(driver:'Driver', current_tab:Tab, _parent_tab:'BrowserTab',  internal_elem:CoreElement):
    if not internal_elem:
        return None
    if internal_elem._node.node_name == "IFRAME":
        return create_iframe_element(driver, current_tab, _parent_tab, internal_elem)
    else:
        return Element(driver, current_tab, _parent_tab,  internal_elem)

def get_all_parents(node):
    if node is None:
        return []

    parents = []
    current_node = node.parent

    while current_node is not None:
        parents.append(current_node)
        current_node = current_node.parent

    return parents

def perform_get_element_at_point(x: int, y: int, child_selector: Optional[str], wait: Optional[int], driver: 'Driver') -> Optional['Element']:
    """
    Gets the element at the specified coordinates and optionally finds a child element matching the selector.
    
    Args:
        x: X coordinate
        y: Y coordinate 
        child_selector: Optional CSS selector to find child element
        wait: Optional timeout to wait for child element
        driver: Driver instance to create elements with
        
    Returns:
        Element at coordinates or matching child element
    """
    elem = driver._tab.get_element_at_point(x, y, wait)
    el = driver._make_element(elem) if elem else None

    if not el:
        return None

    if child_selector:
        selected_el = el.select(child_selector, wait=None)
        if selected_el:
            return selected_el
        else:
            if wait:
                now = time.time()
                while not selected_el:
                    elem = driver._tab.get_element_at_point(x, y, None) 
                    el = driver._make_element(elem) if elem else None
                    if el:
                        selected_el = el.select(child_selector, wait=None)
                    if time.time() - now > wait:
                        return selected_el
                    time.sleep(0.2)
                return selected_el

    return el
def perform_select_options(select_element:'Element', value, index, label):
    if value is None and index is None and label is None:
        raise ValueError("One of 'value', 'index', or 'label' must be provided.")
    if value is not None:
        if isinstance(value, list):
            for v in value:
                select_element.select(f"option[value='{v}']")._elem.perform_select_option()
        else:
            select_element.select(f"option[value='{value}']")._elem.perform_select_option()
    elif index is not None:
        if isinstance(index, list):
            for i in index:
                select_element.select(f"option:nth-child({i + 1})")._elem.perform_select_option()
        else:
            select_element.select(f"option:nth-child({index + 1})")._elem.perform_select_option()
    elif label is not None:
        if isinstance(label, list):
            for l in label:
                select_element.select(f"option[label='{l}']")._elem.perform_select_option()
        else:
            select_element.select(f"option[label='{label}']")._elem.perform_select_option()



def merge_rects(el_rect, tab_rect, ):
        el_rect.x = tab_rect.x + el_rect.x
        el_rect.y = tab_rect.y + el_rect.y
        el_rect.left = tab_rect.left + el_rect.left
        el_rect.top = tab_rect.top + el_rect.top
        return el_rect

class Element:
    def __init__(self, driver:'Driver',  tab: Tab, _parent_tab: 'BrowserTab', elem: CoreElement):
        self._driver = driver
        self._parent_tab = _parent_tab
        self._tab = tab
        self._elem: CoreElement = elem
        self.attributes = self._elem.attrs
    @property
    def text(self):
        return self.run_js("(el) => el.innerText || el.textContent")

    @property
    def html(self):
        return self._elem.get_html()

    @property
    def tag_name(self):
        return self._elem.tag.lower()

    @property
    def parent(self):
        return (
            self._make_element(self._elem.parent)
            if self._elem.parent
            else None
        )

    @property
    def children(self) -> List["Element"]:
        return [self._make_element(e) for e in self._elem.children]

    @property
    def all_parents(self) -> List["Element"]:
        return get_all_parents(self)

    @property
    def src(self):
        return self._elem.attrs.get("src")

    @property
    def href(self):
        return self._elem.attrs.get("href")

    @property
    def value(self):
        return self.run_js("(el) => el.value")

    def get_attribute(self, attribute: str) -> str:
        if attribute == "value":
            return self.value
        return self.attributes.get(attribute)
    # def get_js_properties(self) -> dict:
    #     """
    #     Retrieves the JavaScript properties of the element.

    #     Returns:
    #         dict: A dictionary containing the JavaScript properties of the element.
    #     """
    #     return self._elem.get_js_attributes()    


    def _get_bounding_rect_with_iframe_offset(self):
        self_rect = self.get_bounding_rect()
        parent_rect = self._parent_tab._get_bounding_rect_with_iframe_offset()
        
        
        rect = merge_rects(parent_rect, self_rect, )

        # FIX RECT
        rect.width = self_rect.width
        rect.height = self_rect.height
        rect.center = calc_center(rect)
        
        return rect
    
    def get_bounding_rect(self, absolute=False):
        return self._elem.get_position(absolute)

    def _make_element(self, elem: CoreElement) -> "Element":
        return make_element(self._driver, self._tab, self._parent_tab, elem)

    def get_shadow_root(self, wait: Optional[int] = Wait.SHORT):
        def has_height():
            rect = self.get_bounding_rect()
            if rect.height > 0:
                return rect
            # Let it load
            sleep(0.75)
            return  None
        rect = wait_for_result(has_height, max(wait, Wait.LONG))
        if rect is None:
            raise DriverException("Shadow root cannot be found because the element has no height.")
        x = rect.x
        y = rect.y
        try:
            elem = self._tab.get_element_at_point(x, y, wait)
            return self._make_element(elem) if elem else None
        except:
          return self._make_element(self._elem.first_shadow_root)

    def select(self, selector: str, wait: Optional[int] = Wait.SHORT) -> "Element":
        elem = self._elem.query_selector(selector, wait)
        return self._make_element(elem)

    def select_all(
        self, selector: str, wait: Optional[int] = Wait.SHORT
    ) -> List["Element"]:
        elems = self._elem.query_selector_all(selector, wait)
        return [self._make_element(e) for e in elems]

    def select_iframe(
        self, selector: str, wait: Optional[int] = Wait.SHORT
    ) -> Union["IframeElement", "IframeTab"]:
        return self.select(selector, wait)
    def click(
        self, 
        selector: Optional[str] = None, 
        wait: Optional[int] = Wait.SHORT,
        skip_move: bool = False
    ) -> None:
        """Clicks the element
        
        Args:
            selector: Optional selector to find element
            wait: Maximum time to wait for element
            skip_move: If True, uses direct click instead of human movement, Only applicable when human mode is enabled
        """
        if selector:
            element = self.wait_for_element(selector, wait)
            if self._driver.is_human_mode_enabled:
                self._driver._cursor.click(element, skip_move=skip_move)
            else:
                element.click()
        else:
            if self._driver.is_human_mode_enabled:
                self._driver._cursor.click(self, skip_move=skip_move)
            else:
                self._elem.click()

    def get_element_at_point(
        self,
        x: int,
        y: int, 
        child_selector: Optional[str] = None,
        wait: Optional[int] = Wait.SHORT,
    ) -> 'Element':
        return perform_get_element_at_point(
            *self._get_x_y_with_iframe_offset(x,y),
            child_selector=child_selector, 
            wait=wait,
            driver=self._driver
        )

    def _get_x_y_with_iframe_offset(self,x,y):
        rect = self._get_bounding_rect_with_iframe_offset()
        return (x+rect.x,y+rect.y)
    
    def click_at_point(self, x: int, y:int, skip_move: bool = False):
        if self._driver.is_human_mode_enabled:
            with_human_mode(self._driver, lambda: self._driver._cursor.click(self._get_x_y_with_iframe_offset(x,y), skip_move=skip_move))
        else:
            self._tab.click_at_point(*self._get_x_y_with_iframe_offset(x,y))

    def move_mouse_here(self, is_jump: bool = False):
        """Moves mouse cursor to this element
        
        Args:
            is_jump: If True, instantly jumps to element instead of smooth movement
        """
        with_human_mode(self._driver, lambda: self._driver._cursor.move_to(self, is_jump=is_jump))

    def move_mouse_to_point(self, x: int, y: int, is_jump: bool = False):
        """Moves mouse cursor to specified coordinates
        
        Args:
            x: X coordinate
            y: Y coordinate
            is_jump: If True, instantly jumps to coordinates instead of smooth movement
        """
        with_human_mode(self._driver, lambda: self._driver._cursor.move_mouse_to_point(*self._get_x_y_with_iframe_offset(x,y), is_jump=is_jump))

    def move_mouse_to_element(self, selector: str, wait: Optional[int] = Wait.SHORT, is_jump: bool = False):
        """Moves mouse cursor to element matching selector
        
        Args:
            selector: CSS selector to find element
            wait: Maximum time to wait for element 
            is_jump: If True, instantly jumps to element instead of smooth movement
        """
        elem = self.select(selector, wait)
        if not elem:
            print(f"Element not found for selector: {selector}")
            return False
        else:
            elem.move_mouse_here(is_jump=is_jump)
            return True

    def mouse_press(self, x: int, y:int):
        with_human_mode(self._driver, lambda: self._driver._cursor.mouse_press(*self._get_x_y_with_iframe_offset(x,y)))

    def mouse_release(self, x: int, y:int):
        with_human_mode(self._driver, lambda: self._driver._cursor.mouse_release(*self._get_x_y_with_iframe_offset(x,y)))

    def mouse_press_and_hold(self, x: int, y: int, release_condition: Optional[Callable[[], bool]] = None, release_condition_check_interval: float = 0.5, click_duration: Optional[float] = None):
        with_human_mode(self._driver, lambda: self._driver._cursor.mouse_press_and_hold(*self._get_x_y_with_iframe_offset(x,y), release_condition=release_condition, release_condition_check_interval=release_condition_check_interval, click_duration=click_duration))

    def drag_and_drop_to(self, to_point: Union[tuple[int, int], 'Element']) -> None:
        """
        Drags the current element to the specified destination element or selector.

        Args:
            destination (Union[str, 'Element']): The target element or selector to drag the current element to.
            wait (Optional[int], optional): The time to wait for the destination element to be available. Defaults to Wait.SHORT.

        Returns:
            None
        """
        if isinstance(to_point, (list,tuple)):
            with_human_mode(self._driver, lambda: self._driver._cursor.drag_and_drop(self, *self._get_x_y_with_iframe_offset(*to_point)))
        else:
            with_human_mode(self._driver, lambda: self._driver._cursor.drag_and_drop(self, to_point))

    def type(
        self,
        text: str,
        selector: Optional[str] = None,
        wait: Optional[int] = Wait.SHORT,
    ) -> None:
        if selector:
            self.wait_for_element(selector, wait).type(text)
        else:
            self._elem.send_keys(text)

    def clear(self, selector: Optional[str] = None, wait: Optional[int] = Wait.SHORT) -> None:
        """
        Clears the input field of a web element.
        If a selector is provided, it waits for the element to be present and then clears its input field.
        If no selector is provided, it clears the input field of the current element.
        Args:
            selector (Optional[str]): The CSS selector of the element to clear. Defaults to None.
            wait (Optional[int]): The amount of time to wait for the element to be present. Defaults to Wait.SHORT.
        Returns:
            None
        """

        if selector:
            self.wait_for_element(selector, wait).clear()
        else:
            self._elem.clear_input()

    def focus(self, selector: Optional[str] = None, wait: Optional[int] = Wait.SHORT) -> None:
        """
        Focuses on the element specified by the selector or the current element.

        Args:
            selector (Optional[str], optional): The CSS selector of the element to focus on. Defaults to None.
            wait (Optional[int], optional): The time to wait for the element to be available. Defaults to Wait.SHORT.

        Returns:
            None
        """
        if selector:
            self.wait_for_element(selector, wait).focus()
        else:
            self._elem.focus()


    def set_value(self, value: str) -> None:
        """
        Sets the value of the element.

        Args:
            value (str): The value to set for the element.

        Returns:
            None
        """
        self._elem.set_value(value)

    def set_text(self, text: str) -> None:
        """
        Sets the text content of the element.

        Args:
            text (str): The text to set for the element.

        Returns:
            None
        """
        self._elem.set_text(text)

    def check_element(
        self, selector: Optional[str] = None, wait: Optional[int] = Wait.SHORT
    ) -> None:
        if selector:
            self.wait_for_element(selector, wait).check_element()
        else:
            self._elem.check_element()

    def uncheck_element(
        self, selector: Optional[str] = None, wait: Optional[int] = Wait.SHORT
    ) -> None:
        if selector:
            self.wait_for_element(selector, wait).uncheck_element()
        else:
            self._elem.uncheck_element()

    def select_option(
        self,
        selector: str,
        value: Optional[Union[str, List[str]]] = None,
        index: Optional[Union[int, List[int]]] = None,
        label: Optional[Union[str, List[str]]] = None,
        wait: Optional[int] = Wait.SHORT,
    ) -> None:
        """
        Selects an option from a dropdown element.

        Args:
            selector (str): The CSS selector for the dropdown element.
            value (Optional[Union[str, List[str]]], optional): The value(s) of the option(s) to select. Defaults to None.
            index (Optional[Union[int, List[int]]], optional): The index/indices of the option(s) to select. Defaults to None.
            label (Optional[Union[str, List[str]]], optional): The label(s) of the option(s) to select. Defaults to None.
            wait (Optional[int], optional): The time to wait for the element to be available. Defaults to Wait.SHORT.

        Raises:
            ValueError: If none of 'value', 'index', or 'label' is provided.

        Returns:
            None
            
        Example:
            driver.get("https://www.digitaldutch.com/unitconverter/length.htm")
            driver.select('#calculator').select_option("select#selectFrom", index=17)
            driver.prompt()            
        """
        select_element = self.wait_for_element(selector, wait)        
        perform_select_options(select_element, value, index, label)

    def is_element_present(
        self, selector: str, wait: Optional[int] = Wait.SHORT
    ) -> bool:
        return self.select(selector, wait) is not None

    def get_link(
        self,
        selector: str,
        url_contains_text: Optional[str] = None,
        element_contains_text: Optional[str] = None,
        wait: Optional[int] = Wait.SHORT,
    ) -> str:
        elems = self._elem.query_selector_all(
            selector, timeout=wait, node_name="a"
        )

        for elem in elems:
            if url_contains_text and url_contains_text not in elem.href:
                continue
            if element_contains_text and element_contains_text not in elem.text:
                continue
            return elem.href

        return None

    def get_all_links(
        self,
        selector: str,
        url_contains_text: Optional[str] = None,
        element_contains_text: Optional[str] = None,
        wait: Optional[int] = Wait.SHORT,
    ) -> List[str]:
        elems = self._elem.query_selector_all(
            selector, timeout=wait, node_name="a"
        )

        if url_contains_text:
            elems = [elem for elem in elems if url_contains_text in elem.href]

        if element_contains_text:
            elems = [elem for elem in elems if element_contains_text in elem.text]

        return [elem.href for elem in elems]

    def get_image_link(
        self,
        selector: str,
        url_contains_text: Optional[str] = None,
        element_contains_text: Optional[str] = None,
        wait: Optional[int] = Wait.SHORT,
    ) -> str:
        elems = self._elem.query_selector_all(
            selector, timeout=wait, node_name="img"
        )

        for elem in elems:
            if url_contains_text and url_contains_text not in elem.src:
                continue
            if element_contains_text and element_contains_text not in elem.text:
                continue
            return elem.src

        return None

    def get_all_image_links(
        self,
        selector: str,
        url_contains_text: Optional[str] = None,
        element_contains_text: Optional[str] = None,
        wait: Optional[int] = Wait.SHORT,
    ) -> List[str]:
        elems = self._elem.query_selector_all(
            selector, timeout=wait, node_name="img"
        )

        if url_contains_text:
            elems = [elem for elem in elems if url_contains_text in elem.src]

        if element_contains_text:
            elems = [elem for elem in elems if element_contains_text in elem.text]

        return [elem.src for elem in elems]

    def get_parent_which_satisfies(self, predicate):
        if self is None:
            return None

        current_node = self.parent
        while current_node is not None:
            if predicate(current_node):
                return current_node
            current_node = current_node.parent

        return None

    def get_parent_which_is(self, tag_name):
        def predicate(element):
            return element.tag_name == tag_name

        return self.get_parent_which_satisfies(predicate)

    def wait_for_element(
        self, selector: str, wait: Optional[int] = Wait.SHORT
    ) -> "Element":
        return self._make_element(
            self._elem.wait_for(selector, timeout=wait),
        )

    def remove(self) -> None:
        """
        Removes the element from the DOM.
        """
        self._elem.remove_from_dom()

    def scroll_to_bottom(self, smooth_scroll: bool = True) -> None:
        if smooth_scroll:
            self.run_js(
                r"(el) => el.scrollTo({top: el.scrollHeight, behavior: 'smooth'})"
            )
        else:
            self.run_js(r"(el) => el.scrollTo({top: el.scrollHeight})")

    def can_scroll_further(self) -> bool:
        return self.run_js(
            "(el) => !(Math.abs(el.scrollTop - (el.scrollHeight - el.offsetHeight)) <= 3)"
        )

    def scroll(self, by: int = 1000, smooth_scroll: bool = True) -> None:
        if smooth_scroll:
            self.run_js(
                r"(el) => el.scrollBy({top: BY, behavior: 'smooth'})".replace(
                    "BY", str(by)
                )
            )
        else:
            self.run_js(r"(el) => el.scrollBy({top: BY})".replace("BY", str(by)))

    def scroll_into_view(self) -> None:
        self._elem.scroll_into_view()

    def upload_file(self, file_path: str) -> None:
        ensure_supports_file_upload(self)
        file_path = convert_to_absolute_path(file_path)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        if not os.path.isfile(file_path):
            raise ValueError(f"Path is not a file: {file_path}")        
        self._elem.send_file(file_path)

    def upload_multiple_files(self, file_paths: List[str]) -> None:
        file_paths = [convert_to_absolute_path(file_path) for file_path in file_paths]
        ensure_supports_multiple_upload(self)
        self._elem.send_file(*file_paths)

    def download_video(
        self,
        filename: Optional[str] = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".mp4",
        wait_for_download_completion: bool = True,
        duration: Optional[Union[int, float]] = None,
    ) -> None:
        relative_path = self._elem.download_video(create_video_filename(filename), duration)

        if wait_for_download_completion:
            while not self.is_video_downloaded():
                time.sleep(1)

            print(f"View downloaded video at {relative_path}")

    def is_video_downloaded(self) -> bool:
        return self._elem.is_video_downloaded()

    def save_screenshot(
        self,
        filename: Optional[str] = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".png",
    ) -> None:
        self._elem.save_screenshot(filename)

    def __repr__(self):
        return self._elem.__repr__()

    def run_js(self, script: str, args: Optional[any]=None) -> Any:
        script = load_script_if_js_file(script)
        self._elem.raise_if_disconnected()

        try:
          return self._elem.apply(script,args=args)
        except Exception as e:
          raise




class BrowserTab:
    def __init__(self, config, _tab_value:Tab, _parent_tab:'BrowserTab', _driver:'Driver',_browser:Browser):
        self.config = config
        self._tab_value = _tab_value
        self._browser:Browser = _browser
        self._parent_tab:Browser = _parent_tab 
        self._driver:Browser = _driver 
        self._native_fetch_name = None
        self.responses = Responses(self)

    @property
    def _tab(self) -> Tab:
        if not self._tab_value:
            return self._browser.get_first_tab()
        return self._tab_value

    @_tab.setter
    def _tab(self, value: Tab):
        self._tab_value = value

    @property
    def current_url(self):
        return self.run_js("return window.location.href")

    @property
    def title(self):
        return get_title_safe(self)

    @property
    def page_text(self):
        return self.select("body").text

    @property
    def requests(self):
        from .requests import Request

        return Request(self)

    @property
    def page_html(self):
        return self._tab.get_content()

    @property
    def local_storage(self):
        return LocalStorage(self)


    def _update_targets(self):
        return self._browser.update_targets()


    def prevent_fetch_spying(self) -> Any:
        rand = generate_random_string()
        self.run_on_new_document(f"window.{rand} = window.fetch")
        self._native_fetch_name = rand

    def run_js(self, script: str, args: Optional[any]=None) -> Any:
        script = load_script_if_js_file(script)
        # We will automatically run the script in an Immediately Invoked Function Expression (IIFE)
        return self._tab.evaluate(script,args=args,await_promise=True)

    def run_on_new_document(
        self, script
    ) -> None:
        if script:
            self.run_cdp_command(cdp.page.enable())
            
            return self.run_cdp_command(cdp.page.add_script_to_evaluate_on_new_document(make_iife(load_script_if_js_file(script))))

    def run_cdp_command(self, command) -> Any:
        return self._tab.run_cdp_command(command)


    def before_request_sent(self, handler: Callable[[str, cdp.network.Request, cdp.network.RequestWillBeSent], None]):
        """
        Registers a handler to be called when a request is about to be sent.

        Args:
            handler (Callable[[str, cdp.network.Request, cdp.network.RequestWillBeSent], None]):
                A callback function that will be called before each request is sent.
                The callback receives three arguments:
                    - request_id (str): The unique identifier for the request.
                    - request (cdp.network.Request): The request object containing details like URL, method, headers.
                    - request_will_be_sent (cdp.network.RequestWillBeSent): Additional request metadata.

        Example:
            ```python
            def before_request_handler(request_id, request, request_will_be_sent):
                print(
                    "before_request_handler",
                    {
                        "request_id": request_id,
                        "url": request.url,
                        "method": request.method,
                        "headers": request.headers,
                    },
                )
                driver.responses.append(request_id)

            driver.before_request_sent(before_request_handler)
            driver.get("https://example.com/")
            collected_responses = driver.responses.collect()
            ```
        """
        self._tab.before_request_sent(handler)

    def after_response_received(self, handler: Callable[[str, cdp.network.Response, cdp.network.ResponseReceived], None]):
        """
        Registers a handler to be called when a response is received.

        Args:
            handler (Callable[[str, cdp.network.Response, cdp.network.ResponseReceived], None]):
                A callback function that will be called after each response is received.
                The callback receives three arguments:
                    - request_id (str): The ID of the request.
                    - response (cdp.network.Response): The response object.
                    - event (cdp.network.ResponseReceived): The event object.

        Example:
            ```python
            def after_response_handler(
                request_id: str,
                response: cdp.network.Response,
                event: cdp.network.ResponseReceived,
            ):
                url = response.url
                status = response.status
                headers = response.headers
                print(
                    "after_response_handler",
                    {
                        "request_id": request_id,
                        "url": url,
                        "status": status,
                        "headers": headers,
                    },
                )
                driver.responses.append(request_id)

            driver.after_response_received(after_response_handler)
            driver.get("https://example.com/")
            collected_responses = driver.responses.collect()
            ```
        """
        self._tab.after_response_received(handler)
        
    def collect_response(self, request):
        try:
            body,base64Encoded = self.run_cdp_command(cdp.network.get_response_body(request))
            response = Response(
                    request_id=request,
                    content=body,
                    is_base_64=base64Encoded,
                )
                
        except ChromeException as e:
          if "No data found for resource" in e.message:
            response = Response(
                    request_id=request,
                    content=None,
                    is_base_64=False,
                )
            
        return response
    
    def collect_responses(self, request_ids):
        return [self.collect_response(request_id) for request_id in request_ids]    


    def get_js_variable(self, variable_name: str) -> Any:
        return self._tab.js_dumps(variable_name)

    def select(self, selector: str, wait: Optional[int] = Wait.SHORT) -> Element:
        elem = self._tab.select(selector, timeout=wait)
        return self._make_element(elem) if elem else None
    

    def select_all(
        self, selector: str, wait: Optional[int] = Wait.SHORT
    ) -> List[Element]:
        elems = self._tab.select_all(selector, timeout=wait)
        return [self._make_element(e) for e in elems]
    
    def count(
        self, selector: str, wait: Optional[int] = Wait.SHORT
    ) -> int:
        return self._tab.count_select(selector, timeout=wait)


    def select_iframe(
        self, selector: str, wait: Optional[int] = Wait.SHORT
    ) -> Union["IframeElement", "IframeTab"]:
        return self.select(selector, wait)

    def get_element_containing_text(
        self,
        text: str,
        wait: Optional[int] = Wait.SHORT,
        type: Optional[str] = None,
    ) -> Element:
        elem = self._tab.find(text, type=type, timeout=wait)
        return self._make_element(elem) if elem else None

    def get_all_elements_containing_text(
        self,
        text: str,
        wait: Optional[int] = Wait.SHORT,
        type: Optional[str] = None,
    ) -> List[Element]:
        elems = self._tab.find_all(text, type=type, timeout=wait)
        return [self._make_element(e) for e in elems]

    def get_element_with_exact_text(
        self,
        text: str,
        wait: Optional[int] = Wait.SHORT,
        type: Optional[str] = None,
    ) -> Element:
        elem = self._tab.find(text, type=type, timeout=wait, exact_match=True)
        return self._make_element(elem) if elem else None

    def get_all_elements_with_exact_text(
        self,
        text: str,
        wait: Optional[int] = Wait.SHORT,
        type: Optional[str] = None,
    ) -> List[Element]:
        elems = self._tab.find_all(text, type=type, timeout=wait, exact_match=True)
        return [self._make_element(e) for e in elems]

    def get_element_at_point(
        self,
        x: int,
        y: int, 
        child_selector: Optional[str] = None,
        wait: Optional[int] = Wait.SHORT,
    ) -> Element:
        return perform_get_element_at_point(
            x=x,
            y=y,
            child_selector=child_selector, 
            wait=wait,
            driver=self
        )

    def _get_driver(self):
        return self

    def _get_x_y_with_iframe_offset(self,x,y):
        rect = self._get_bounding_rect_with_iframe_offset()
        return (x+rect.x,y+rect.y)

    def click_at_point(self, x: int, y:int, skip_move: bool = False):
        if self.is_human_mode_enabled: 
            with_human_mode(self, lambda: self._get_driver()._cursor.click(self._get_x_y_with_iframe_offset(x,y), skip_move=skip_move))
        else:
            self._tab.click_at_point(*self._get_x_y_with_iframe_offset(x,y))

    def move_mouse_to_point(self, x: int, y: int, is_jump: bool = False):
        """Moves mouse cursor to specified coordinates
        
        Args:
            x: X coordinate
            y: Y coordinate
            is_jump: If True, instantly jumps to coordinates instead of smooth movement
        """
        with_human_mode(self._get_driver(), lambda: self._get_driver()._cursor.move_mouse_to_point(*self._get_x_y_with_iframe_offset(x,y), is_jump=is_jump))

    def move_mouse_to_element(self, selector: str, wait: Optional[int] = Wait.SHORT, is_jump: bool = False):
        """Moves mouse cursor to element matching selector
        
        Args:
            selector: CSS selector to find element
            wait: Maximum time to wait for element
            is_jump: If True, instantly jumps to element instead of smooth movement
        """
        elem = self.select(selector, wait)
        if not elem:
            print(f"Element not found for selector: {selector}")
            return False
        else:
            elem.move_mouse_here(is_jump=is_jump)
            return True
        
    def mouse_press(self, x: int, y:int):
        with_human_mode(self._get_driver(), lambda: self._get_driver()._cursor.mouse_press(*self._get_x_y_with_iframe_offset(x,y)))

    def mouse_release(self, x: int, y:int):
        with_human_mode(self._get_driver(), lambda: self._get_driver()._cursor.mouse_release(*self._get_x_y_with_iframe_offset(x,y)))

    def mouse_press_and_hold(self, x: int, y: int, release_condition: Optional[Callable[[], bool]] = None, release_condition_check_interval: float = 0.5, click_duration: Optional[float] = None):
        with_human_mode(self._get_driver(), lambda: self._get_driver()._cursor.mouse_press_and_hold(*self._get_x_y_with_iframe_offset(x,y), release_condition=release_condition, release_condition_check_interval=release_condition_check_interval, click_duration=click_duration))

    def drag_and_drop(self, from_point: tuple[int, int], to_point: tuple[int, int] ) -> None:
            """
            Drags the current element to the specified destination element or selector.

            Args:
                destination (Union[str, 'Element']): The target element or selector to drag the current element to.
                wait (Optional[int], optional): The time to wait for the destination element to be available. Defaults to Wait.SHORT.

            Returns:
                None
            """
            with_human_mode(self._get_driver(), lambda: self._get_driver()._cursor.drag_and_drop(from_point, to_point))
            

    def get_iframe_by_link(
        self, link_regex: Optional[str] = None, wait: Optional[int] = Wait.SHORT
    )-> Union["IframeElement", "IframeTab"]:
        return get_iframe_elem_by_link(self._driver,  self._tab, self,  link_regex, wait)


    def is_element_present(self, selector: str, wait: Optional[int] = None) -> bool:
        return self.select(selector, wait) is not None

    def click(
        self, 
        selector: str, 
        wait: Optional[int] = Wait.SHORT,
        skip_move: bool = False
    ) -> None:
        elem = self.wait_for_element(selector, wait)
        elem.click(skip_move=skip_move)



    def click_element_containing_text(
        self, 
        text: str, 
        wait: Optional[int] = Wait.SHORT,
        skip_move: bool = False
    ) -> None:
        elem = self.get_element_containing_text(text, wait)

        if elem is None:
            raise ElementWithTextNotFoundException(text)

        elem.click(skip_move=skip_move)

    def type(self, selector: str, text: str, wait: Optional[int] = Wait.SHORT) -> None:
        elem = self.wait_for_element(selector, wait)
        elem.type(text)

    def type_by_label(
        self, label: str, text: str, wait: Optional[int] = Wait.SHORT
    ) -> None:
        input_elem = get_input_el(self, label, wait, "text")
        if input_elem:
            input_elem.type(text)
        else:
            raise InputElementForLabelNotFoundException(label)


    def clear(self, selector: str, wait: Optional[int] = Wait.SHORT) -> None:
        """
        Clears the text from the input element specified by the selector.
        Args:
            selector (str): The CSS selector of the element to clear.
            wait (Optional[int], optional): The maximum time to wait for the element to be present. Defaults to Wait.SHORT.
        Returns:
            None
        """
        el = self.wait_for_element(selector, wait)
        el.clear()
        
    def focus(self, selector: str, wait: Optional[int] = Wait.SHORT) -> None:
        """
        Focuses on the element specified by the selector.

        Args:
            selector (str): The CSS selector of the element to focus on.
            wait (Optional[int], optional): The time to wait for the element to be available. Defaults to Wait.SHORT.

        Returns:
            None
        """
        el = self.wait_for_element(selector, wait)
        el.focus()


    def set_value(self, selector: str, value: str, wait: Optional[int] = Wait.SHORT) -> None:
        """
        Sets the value of the element specified by the selector.

        Args:
            selector (str): The CSS selector of the element.
            value (str): The value to set for the element.
            wait (Optional[int], optional): The time to wait for the element to be available. Defaults to Wait.SHORT.

        Returns:
            None
        """
        el = self.wait_for_element(selector, wait)
        el.set_value(value)

    def set_text(self, selector: str, text: str, wait: Optional[int] = Wait.SHORT) -> None:
        """
        Sets the text content of the element specified by the selector.

        Args:
            selector (str): The CSS selector of the element.
            text (str): The text to set for the element.
            wait (Optional[int], optional): The time to wait for the element to be available. Defaults to Wait.SHORT.

        Returns:
            None
        """
        el = self.wait_for_element(selector, wait)
        el.set_text(text)
        

    def check_element(self, selector: str, wait: Optional[int] = Wait.SHORT) -> None:
        elem = self.wait_for_element(selector, wait)
        elem.check_element()

    def check_element_by_label(
        self, label: str, wait: Optional[int] = Wait.SHORT
    ) -> None:
        input_elem = get_input_el(self, label, wait, "checkbox")
        if input_elem:
            input_elem.check_element()
        else:
            raise CheckboxElementForLabelNotFoundException(label)

    def get_input_by_label(
        self, label: str, wait: Optional[int] = Wait.SHORT
    ) -> Element:
        input_elem = get_input_el(self, label, wait, "any")
        if input_elem:
            return input_elem
        else:
            raise InputElementForLabelNotFoundException(label)

    def uncheck_element(self, selector: str, wait: Optional[int] = Wait.SHORT) -> None:
        elem = self.wait_for_element(selector, wait)
        elem.uncheck_element()

    def uncheck_element_by_label(
        self, label: str, wait: Optional[int] = Wait.SHORT
    ) -> None:
        input_elem = get_input_el(self,label, wait, "checkbox")
        if input_elem:
            input_elem.uncheck_element()
        else:
            raise CheckboxElementForLabelNotFoundException(label)

    def select_option(
        self,
        selector: str,
        value: Optional[Union[str, List[str]]] = None,
        index: Optional[Union[int, List[int]]] = None,
        label: Optional[Union[str, List[str]]] = None,
        wait: Optional[int] = Wait.SHORT,
    ) -> None:
        """
        Selects an option from a dropdown element specified by the selector.

        Args:
            selector (str): The CSS selector for the dropdown element.
            value (Optional[Union[str, List[str]]], optional): The value(s) of the option(s) to select. Defaults to None.
            index (Optional[Union[int, List[int]]], optional): The index/indices of the option(s) to select. Defaults to None.
            label (Optional[Union[str, List[str]]], optional): The label(s) of the option(s) to select. Defaults to None.
            wait (Optional[int], optional): The time to wait for the element to be available. Defaults to Wait.SHORT.

        Raises:
            ValueError: If none of 'value', 'index', or 'label' is provided.

        Returns:
            None

        Example:
            driver.get("https://www.digitaldutch.com/unitconverter/length.htm")
            driver.select_option("select#selectFrom", index=17)
            driver.prompt()
        """
        select_element = self.wait_for_element(selector, wait)
        perform_select_options(select_element, value, index, label)


    def get_link(
        self,
        selector: str,
        url_contains_text: Optional[str] = None,
        element_contains_text: Optional[str] = None,
        wait: Optional[int] = Wait.SHORT,
    ) -> str:
        elems = self._tab.select_all(selector, timeout=wait, node_name="a")

        for elem in elems:
            if url_contains_text and url_contains_text not in elem.href:
                continue
            if element_contains_text and element_contains_text not in elem.text:
                continue
            return elem.href

        return None

    def get_all_links(
        self,
        selector: Optional[str] = None,
        url_contains_text: Optional[str] = None,
        element_contains_text: Optional[str] = None,
        wait: Optional[int] = Wait.SHORT,
    ) -> List[str]:
        elems = self._tab.select_all(
            selector if selector else "a[href]", timeout=wait, node_name="a"
        )

        if url_contains_text:
            elems = [elem for elem in elems if url_contains_text in elem.href]
        if element_contains_text:
            elems = [elem for elem in elems if element_contains_text in elem.text]
        return [elem.href for elem in elems]

    def get_image_link(
        self,
        selector: str,
        url_contains_text: Optional[str] = None,
        element_contains_text: Optional[str] = None,
        wait: Optional[int] = Wait.SHORT,
    ) -> str:
        elems = self._tab.select_all(selector, timeout=wait, node_name="img")

        for elem in elems:
            if url_contains_text and url_contains_text not in elem.src:
                continue
            if element_contains_text and element_contains_text not in elem.text:
                continue
            return elem.src

        return None

    def get_all_image_links(
        self,
        selector: Optional[str] = None,
        url_contains_text: Optional[str] = None,
        element_contains_text: Optional[str] = None,
        wait: Optional[int] = Wait.SHORT,
    ) -> List[str]:
        elems = self._tab.select_all(
            selector if selector else "img[src]", timeout=wait, node_name="img"
        )

        if url_contains_text:
            elems = [elem for elem in elems if url_contains_text in elem.src]

        if element_contains_text:
            elems = [elem for elem in elems if element_contains_text in elem.text]

        return [elem.src for elem in elems]

    def get_text(self, selector: str, wait: Optional[int] = Wait.SHORT) -> str:
        elem = self.wait_for_element(selector, wait)
        return elem.text

    def wait_for_element(
        self, selector: str, wait: Optional[int] = Wait.SHORT
    ) -> Element:
        return self._make_element(self._tab.wait_for(selector, timeout=wait))

    def remove(self, selector: str, wait: Optional[int] = Wait.SHORT) -> None:
        """
        Removes the element specified by the selector from the DOM.

        Args:
            selector (str): The CSS selector of the element to remove.
            wait (Optional[int], optional): The time to wait for the element to be available. Defaults to Wait.SHORT.

        Returns:
            None
        """
        el = self.wait_for_element(selector, wait)
        el.remove()    

    def get_attribute(
        self, selector: str, attribute: str, wait: Optional[int] = Wait.SHORT
    ) -> str:
        el = self.wait_for_element(selector, wait)
        return el.attributes.get(attribute)

    def get_all_attributes(
        self, selector: str, wait: Optional[int] = Wait.SHORT
    ) -> dict:
        el = self.wait_for_element(selector, wait)
        return el.attributes
    # def get_js_properties(self, selector: str, wait: Optional[int] = Wait.SHORT) -> dict:
    #     """
    #     Retrieves the JavaScript properties of the element specified by the selector.

    #     Args:
    #         selector (str): The CSS selector of the element.
    #         wait (Optional[int], optional): The time to wait for the element to be available. Defaults to Wait.SHORT.

    #     Returns:
    #         dict: A dictionary containing the JavaScript properties of the element.
    #     """
    #     el = self.wait_for_element(selector, wait)
    #     return el.get_js_properties()
    def scroll_to_bottom(
        self,
        selector: Optional[str] = None,
        smooth_scroll: bool = True,
        wait: Optional[int] = Wait.SHORT,
    ) -> None:
        if selector:
            el = self.wait_for_element(selector, wait)
            el.scroll_to_bottom(smooth_scroll=smooth_scroll)
        else:
            if smooth_scroll:
                self.run_js(
                    r"""window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'});"""
                )
            else:
                self.run_js(r"""window.scrollTo({top: document.body.scrollHeight});""")

    def can_scroll_further(
        self, selector: Optional[str] = None, wait: Optional[int] = Wait.SHORT
    ) -> bool:
        if selector:
            el = self.wait_for_element(selector, wait)
            return el.can_scroll_further()
        else:
            return self.run_js(
                r"""return !(Math.abs(document.body.scrollHeight - (window.innerHeight + window.scrollY)) <= 3)"""
            )

    def scroll(
        self,
        selector: Optional[str] = None,
        by: int = 1000,
        smooth_scroll: bool = True,
        wait: Optional[int] = Wait.SHORT,
    ) -> None:
        if selector:
            el = self.wait_for_element(selector, wait)
            return el.scroll(by, smooth_scroll)
        else:
            if smooth_scroll:
                return self.run_js(
                    r"""window.scrollBy({top:BY, behavior: 'smooth'});""".replace(
                        "BY", str(by)
                    )
                )
            else:
                return self.run_js(
                    r"""window.scrollBy({top:BY});""".replace("BY", str(by))
                )

    def scroll_into_view(self, selector: str, wait: Optional[int] = Wait.SHORT) -> None:
        el = self.wait_for_element(selector, wait)
        el.scroll_into_view()

    def upload_file(
        self, selector: str, file_path: str, wait: Optional[int] = Wait.SHORT
    ) -> None:
        el = self.wait_for_element(selector, wait)
        el.upload_file(file_path)

    def upload_multiple_files(
        self, selector: str, file_paths: List[str], wait: Optional[int] = Wait.SHORT
    ) -> None:
        el = self.wait_for_element(selector, wait)
        el.upload_multiple_files(file_paths)


    def get_bot_detected_by(self) -> str:
        if (
            self.title == "Just a moment..."
        ):
            return Opponent.CLOUDFLARE
        if self.select('[name="cf-turnstile-response"]:not(#cf-invisible-turnstile [name="cf-turnstile-response"])', None):
            return Opponent.CLOUDFLARE
        
        pmx = self.get_element_containing_text(
            "Please verify you are a human", wait=None
        )

        if pmx is not None:
            return Opponent.PERIMETER_X

        return None

    def is_bot_detected(self) -> bool:
        return self.get_bot_detected_by() is not None

    def is_bot_detected_by_cloudflare(self) -> bool:
        opponent = self.get_bot_detected_by()
        return opponent == Opponent.CLOUDFLARE

    def prompt_to_solve_captcha(self) -> None:
        print("")
        print("   __ _ _ _    _                          _       _           ")
        print("  / _(_) | |  (_)                        | |     | |          ")
        print(" | |_ _| | |   _ _ __      ___ __ _ _ __ | |_ ___| |__   __ _ ")
        print(r" |  _| | | |  | | `_ \    / __/ _` | `_ \| __/ __| `_ \ / _` |")
        print(" | | | | | |  | | | | |  | (_| (_| | |_) | || (__| | | | (_| |")
        print(r" |_| |_|_|_|  |_|_| |_|   \___\__,_| .__/ \__\___|_| |_|\__,_|")
        print("                                   | |                        ")
        print("                                   |_|                        ")
        print("")

        return self.prompt(
            "Press fill in the captcha, then press enter to continue ..."
        )

    def prompt(self, text="Press Enter To Continue..."):
        return beep_input(text, self.config.beep)

    def detect_and_bypass_cloudflare(self) -> None:
        bypass_if_detected(self)

    def get_cookies_dict(self):
        all_cookies = self.get_cookies()
        cookies_dict = {}
        for cookie in all_cookies:
            cookies_dict[cookie["name"]] = cookie["value"]
        return cookies_dict

    def get_cookies(self) -> List[dict]:
        return self._browser.cookies.get_all()

    def get_local_storage(self) -> dict:
        storage = self.local_storage
        return storage.items()

    def get_cookies_and_local_storage(self) -> tuple:
        cookies = self.get_cookies()
        local_storage = self.get_local_storage()

        return {"cookies": cookies, "local_storage": local_storage}

    def add_cookies(self, cookies: List[dict]) -> None:
        return self._browser.cookies.set_all(cookies)

    def add_local_storage(self, local_storage: dict) -> None:
        storage = self.local_storage
        for key in local_storage:
            storage.set_item(key, local_storage[key])

    def add_cookies_and_local_storage(self, site_data: dict) -> None:
        cookies = site_data["cookies"]
        local_storage = site_data["local_storage"]
        self.add_cookies(cookies)
        self.add_local_storage(local_storage)

    def delete_cookies(self) -> None:
        return self._browser.cookies.clear()

    def delete_local_storage(self) -> None:
        self.run_js("window.localStorage.clear();")
        self.run_js("window.sessionStorage.clear();")

    def delete_cookies_and_local_storage(self) -> None:
        self.delete_cookies()
        self.delete_local_storage()

    def save_screenshot(
        self,
        filename: Optional[str] = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".png",
    ) -> None:
        self._tab.save_screenshot(filename=filename)

    def save_element_screenshot(
        self,
        selector: str,
        filename: Optional[str] = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".png",
        wait: Optional[int] = Wait.SHORT,
    ) -> None:
        el = self.wait_for_element(selector, wait)
        el.save_screenshot(filename)

    def download_element_video(
        self,
        selector: str,
        filename: Optional[str] = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".mp4",
        wait_for_download_completion: bool = True,
        duration: Optional[Union[int, float]] = None,
        wait: Optional[int] = Wait.SHORT,
    ) -> None:
        el = self.wait_for_element(selector, wait)
        el.download_video(filename, wait_for_download_completion, duration)

    def is_element_video_downloaded(
        self, selector: str, wait: Optional[int] = Wait.SHORT
    ) -> bool:
        el = self.wait_for_element(selector, wait)
        return el.is_video_downloaded()

    def download_file(self, url: str, filename: Optional[str] = None) -> None:
        # if filename not provided, then try getting filename from url response, else fallback to default datetime filename
        self._tab.download_file(url, filename)

    def __repr__(self):
        return self._tab.__repr__()


class IframeTab(BrowserTab):

    def __init__(self, iframe_elem:Element, config, _tab_value:Tab, _parent_tab:'BrowserTab', driver:'Driver', _browser:Browser):
        self.iframe_elem = iframe_elem
        # iframe_elem can be none if using get_iframe_by_link and iframe is in shadowroot, todo: figure out how to get iframe el or coords of a tab, this will fix _get_bounding_rect_with_iframe_offset which will be wrong if using get_iframe_by_link and iframe is in shadowroot
        super().__init__(config, _tab_value, _parent_tab, driver, _browser)
        # self.run_cdp_command(cdp.runtime.disable())


    def _make_element(self, elem):
        return make_element(self._driver, self._tab, self, elem)

    def _get_bounding_rect_with_iframe_offset(self):
        rect = self._parent_tab._get_bounding_rect_with_iframe_offset()
        if self.iframe_elem:
            iframe_elem_rect = self.iframe_elem.get_bounding_rect()
            return merge_rects(iframe_elem_rect, rect, )
        return rect

    def _get_driver(self):
        return self._driver

    def scroll_into_view(self, selector: str = None, wait: Optional[int] = Wait.SHORT) -> None:
        if selector:
            el = self.wait_for_element(selector, wait)
            el.scroll_into_view()
        else: 
            self._get_iframe_elem().scroll_into_view()

    @property
    def iframe_url(self) -> str:
        return self._tab_value.target.url

    def get_bounding_rect(self, absolute=False):
        # Ideally, this method should not be added, but we added it because users who use self.select instead of self.select_iframe get types of Element instead of IframeTab. We added these properties so users get the correct result when they call them.
        return self.select('body').get_bounding_rect(absolute)

    def get_shadow_root(self, wait: Optional[int] = Wait.SHORT):
        # Ideally, this method should not be added, but we added it because users who use self.select instead of self.select_iframe get types of Element instead of IframeTab. We added these properties so users get the correct result when they call them.
        return self.select('body').get_shadow_root(wait)
    
    def move_mouse_here(self, is_jump: bool = False):
        """Moves mouse cursor to this element
        
        Args:
            is_jump: If True, instantly jumps to element instead of smooth movement
        """        
        self._get_iframe_elem().move_mouse_here(is_jump=is_jump)

    def _get_iframe_elem(self):
        if self.iframe_elem:
            return self.iframe_elem
        else:
            raise DriverException("This method is not supported if the iframe is found using get_iframe_by_link().")

    @property
    def text(self):
        # Ideally, this method should not be added, but we added it because users who use self.select instead of self.select_iframe get types of Element instead of IframeTab. We added these properties so users get the correct result when they call them.
        return self.page_html

    @property
    def html(self):
        # Ideally, this method should not be added, but we added it because users who use self.select instead of self.select_iframe get types of Element instead of IframeTab. We added these properties so users get the correct result when they call them.
        return self.page_text

    @property
    def tag_name(self):
        # Ideally, this method should not be added, but we added it because users who use self.select instead of self.select_iframe get types of Element instead of IframeTab. We added these properties so users get the correct result when they call them.
        return 'iframe'
        

class IframeElement(BrowserTab):
    def __init__(self, elem: Element, doc_elem: Element, config, _tab_value:Tab, _parent_tab:'BrowserTab',driver:'Driver',  _browser:Browser):
        self.elem  = elem
        self.doc_elem  = doc_elem
        super().__init__(config, _tab_value, _parent_tab, driver,_browser)

    def raise_unavailable_error(self) -> Tab:
        """
        Raises an exception indicating that the method is not supported in this type of iframe.
        """
        raise UnavailableMethodError("This method is not supported in this type of iframe.")

    @property
    def iframe_url(self) -> str:
        return self.elem._elem.content_document.document_url

    @property
    def current_url(self):
        return self.iframe_url

    @property
    def page_html(self):
        return self.doc_elem.html

    @property
    def local_storage(self):
        return LocalStorage(self)

    def _update_targets(self):
        self.raise_unavailable_error()

    def prevent_fetch_spying(self) -> Any:
        self.raise_unavailable_error()

    def run_js(self, script: str, args: Optional[any]=None) -> Any:
        return self.doc_elem.run_js(script, args)

    def run_on_new_document(
        self, script
    ) -> None:
        self.raise_unavailable_error()

    def run_cdp_command(self, command) -> Any:
        self.raise_unavailable_error()

    def before_request_sent(self, handler: Callable[[str, cdp.network.Request, cdp.network.RequestWillBeSent], None]):
        self.raise_unavailable_error()

    def after_response_received(self, handler: Callable[[str, cdp.network.Response, cdp.network.ResponseReceived], None]):
        self.raise_unavailable_error()
        
    def collect_response(self, request):
        self.raise_unavailable_error()
    
    def collect_responses(self, request_ids):
        self.raise_unavailable_error()

    def get_js_variable(self, variable_name: str) -> Any:
        return self.doc_elem._elem.js_dumps(variable_name)

    def select(self, selector: str, wait: Optional[int] = Wait.SHORT) -> Element:
        return self.elem.select(selector, wait)
    

    def select_all(
        self, selector: str, wait: Optional[int] = Wait.SHORT
    ) -> List[Element]:
        return self.elem.select_all(selector, wait)
    
    def count(
        self, selector: str, wait: Optional[int] = Wait.SHORT
    ) -> int:
        return self._tab.count_select(selector, timeout=wait, _node = self.elem._elem)

    
    def _make_element(self, elem):
        return make_element(self._driver, self._tab, self._parent_tab, elem)

    def get_element_containing_text(
        self,
        text: str,
        wait: Optional[int] = Wait.SHORT,
        type: Optional[str] = None,
    ) -> Element:
        elem = self._tab.find_iframe(text, self.elem._elem,type=type, timeout=wait)
        return self._make_element(elem) if elem else None

    def get_all_elements_containing_text(
        self,
        text: str,
        wait: Optional[int] = Wait.SHORT,
        type: Optional[str] = None,
    ) -> List[Element]:
        elems = self._tab.find_all_iframe(text, self.elem._elem,type=type, timeout=wait)
        return [self._make_element(e) for e in elems]

    def get_element_with_exact_text(
        self,
        text: str,
        wait: Optional[int] = Wait.SHORT,
        type: Optional[str] = None,
    ) -> Element:
        elem = self._tab.find_iframe(text, self.elem._elem,type=type, timeout=wait, exact_match=True)
        return self._make_element(elem) if elem else None

    def get_all_elements_with_exact_text(
        self,
        text: str,
        wait: Optional[int] = Wait.SHORT,
        type: Optional[str] = None,
    ) -> List[Element]:
        elems = self._tab.find_all_iframe(text, self.elem._elem,type=type, timeout=wait, exact_match=True)
        return [self._make_element(e) for e in elems]


    def _get_driver(self):
        return self._driver


    def move_mouse_here(self, is_jump: bool = False):
        """Moves mouse cursor to this element
        
        Args:
            is_jump: If True, instantly jumps to element instead of smooth movement
        """        
        self.elem.move_mouse_here(is_jump=is_jump)

    def get_iframe_by_link(
        self, link_regex: Optional[str] = None, wait: Optional[int] = Wait.SHORT
    )->  Union["IframeElement", "IframeTab"]:
        return get_iframe_elem_by_link(self._driver,  self._tab, self._parent_tab, link_regex, wait)

    def click_element_containing_text(
        self, 
        text: str, 
        wait: Optional[int] = Wait.SHORT,
        skip_move: bool = False
    ) -> None:
        elem = self.get_element_containing_text(text, wait)

        if elem is None:
            raise ElementWithTextNotFoundException(text)

        elem.click(skip_move=skip_move)

    def get_link(
        self,
        selector: str,
        url_contains_text: Optional[str] = None,
        element_contains_text: Optional[str] = None,
        wait: Optional[int] = Wait.SHORT,
    ) -> str:
        elems = self._tab.select_all(selector, timeout=wait, node_name="a", _node = self.elem._elem)
        
        for elem in elems:
            if url_contains_text and url_contains_text not in elem.href:
                continue
            if element_contains_text and element_contains_text not in elem.text:
                continue
            return elem.href

        return None

    def get_all_links(
        self,
        selector: Optional[str] = None,
        url_contains_text: Optional[str] = None,
        element_contains_text: Optional[str] = None,
        wait: Optional[int] = Wait.SHORT,
    ) -> List[str]:
        elems = self._tab.select_all(
            selector if selector else "a[href]", timeout=wait, node_name="a", _node = self.elem._elem
        )

        if url_contains_text:
            elems = [elem for elem in elems if url_contains_text in elem.href]
        if element_contains_text:
            elems = [elem for elem in elems if element_contains_text in elem.text]
        return [elem.href for elem in elems]

    def get_image_link(
        self,
        selector: str,
        url_contains_text: Optional[str] = None,
        element_contains_text: Optional[str] = None,
        wait: Optional[int] = Wait.SHORT,
    ) -> str:
        elems = self._tab.select_all(selector, timeout=wait, node_name="img",  _node = self.elem._elem)

        for elem in elems:
            if url_contains_text and url_contains_text not in elem.src:
                continue
            if element_contains_text and element_contains_text not in elem.text:
                continue
            return elem.src

        return None

    def get_all_image_links(
        self,
        selector: Optional[str] = None,
        url_contains_text: Optional[str] = None,
        element_contains_text: Optional[str] = None,
        wait: Optional[int] = Wait.SHORT,
    ) -> List[str]:
        elems = self._tab.select_all(
            selector if selector else "img[src]", timeout=wait, node_name="img", _node = self.elem._elem
        )

        if url_contains_text:
            elems = [elem for elem in elems if url_contains_text in elem.src]

        if element_contains_text:
            elems = [elem for elem in elems if element_contains_text in elem.text]

        return [elem.src for elem in elems]

    def wait_for_element(
        self, selector: str, wait: Optional[int] = Wait.SHORT
    ) -> Element:
        return self.elem.wait_for_element(selector, wait)

    def save_screenshot(
        self,
        filename: Optional[str] = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".png",
    ) -> None:
        self.elem.save_screenshot(filename=filename)

    def download_file(self, url: str, filename: Optional[str] = None) -> None:
        # if filename not provided, then try getting filename from url response, else fallback to default datetime filename
        self._tab.download_file(url, filename, self.elem._elem)

    def __repr__(self):
        return self.elem.__repr__()
    

    def _get_bounding_rect_with_iframe_offset(self):
        rect = self._parent_tab._get_bounding_rect_with_iframe_offset()
        iframe_elem_rect = self.get_bounding_rect()
        return merge_rects(iframe_elem_rect, rect,)
    
    def get_bounding_rect(self, absolute=False):
        # Ideally, this method should not be added, but we added it because users who use self.select instead of self.select_iframe get types of Element instead of IframeTab. We added these properties so users get the correct result when they call them.
        return self.elem.get_bounding_rect(absolute)

    def get_shadow_root(self, wait: Optional[int] = Wait.SHORT):
        # Ideally, this method should not be added, but we added it because users who use self.select instead of self.select_iframe get types of Element instead of IframeTab. We added these properties so users get the correct result when they call them.
        return self.elem.get_shadow_root(wait)

    @property
    def text(self):
        # Ideally, this method should not be added, but we added it because users who use self.select instead of self.select_iframe get types of Element instead of IframeTab. We added these properties so users get the correct result when they call them.
        return self.page_text

    @property
    def html(self):
        # Ideally, this method should not be added, but we added it because users who use self.select instead of self.select_iframe get types of Element instead of IframeTab. We added these properties so users get the correct result when they call them.
        return self.page_html

    @property
    def tag_name(self):
        # Ideally, this method should not be added, but we added it because users who use self.select instead of self.select_iframe get types of Element instead of IframeTab. We added these properties so users get the correct result when they call them.
        return 'iframe'

def get_iframe_tab(driver, internal_elem):
    iframe_tab = None
    all_targets = driver._browser.targets
    internal_frame_id = str(internal_elem.frame_id)
    for tgt in all_targets:
        if str(tgt.target.target_id) == internal_frame_id:
            iframe_tab = tgt
            break
    return iframe_tab





    # wait_till_document_is_ready(iframe_tab, True)


def get_iframe_element_or_tab(iframe_tab:Tab, driver:'Driver', current_tab:Tab, _parent_tab:BrowserTab, internal_elem:CoreElement):
    elem = Element(driver, current_tab,  _parent_tab,internal_elem)
    if iframe_tab:
        
        return IframeTab(elem, driver.config, iframe_tab, _parent_tab, driver, driver._browser)
    internal_elem.tree = internal_elem.content_document
    doc_elem = Element(driver,   current_tab, _parent_tab, CoreElement(internal_elem.content_document, current_tab, internal_elem.tree))
    return IframeElement(elem, doc_elem, driver.config, current_tab,  _parent_tab, driver, driver._browser)

def create_iframe_element(driver:'Driver', current_tab:Tab, _parent_tab:BrowserTab, internal_elem:CoreElement):
    iframe_tab = get_iframe_tab(driver, internal_elem)
    return get_iframe_element_or_tab(iframe_tab, driver, current_tab, _parent_tab, internal_elem)


def get_iframe_elem_by_link(driver:'BrowserTab', current_tab:Tab, _parent_tab:BrowserTab, link, timeout):
    iframe_tab = get_iframe_tab_by_link(driver, link, timeout)
    el = select_and_find_iframe_el(driver, link)
    if iframe_tab:
        if el:
          if isinstance(el, IframeTab):
            return el
          else: 
            return get_iframe_element_or_tab(iframe_tab, driver, current_tab, _parent_tab, el._elem)
        else:
          return IframeTab(None, driver.config, iframe_tab, _parent_tab, driver, driver._browser)
        
            
    
    return el

def select_and_find_iframe_el(driver, link):
    iframes = driver.select_all("iframe")
    for el in iframes:
        url = el.iframe_url
        if matches_regex(url, link):
            return el


def matches_regex(s, pattern):
    import re

    # Compile the regex pattern
    regex = re.compile(pattern)
    # Use the search method to find a match
    match = regex.search(s)
    # Return True if a match is found, False otherwise
    return bool(match)


def _perform_get_frame(driver, link):
    all_targets = driver._browser.targets
    for tgt in all_targets:
        # print(tgt.target.type_)
        if str(tgt.target.type_) == "iframe":
            # print(tgt.target)
            if link:
                # print(tgt.target.url)
                if matches_regex(tgt.target.url, link):
                    return tgt
            else:
                return tgt


def get_iframe_tab_by_link(driver, link, timeout):
    iframe_tab = _perform_get_frame(driver, link)

    if iframe_tab:
        return iframe_tab

    if timeout:
        start_time = time.time()
        while True:
            iframe_tab = _perform_get_frame(driver, link)
            if iframe_tab:
                return iframe_tab

            driver._update_targets()

            if time.time() - start_time > timeout:
                return None

            time.sleep(0.1)


def get_for_input_selector(type, for_attr):
    if type == "text":
        return f"input[id='{for_attr}'], textarea[id='{for_attr}']"
    elif type == "checkbox":
        return f"input[id='{for_attr}']"
    else:
        return f"input[id='{for_attr}'], textarea[id='{for_attr}'], select[id='{for_attr}']"

def get_title_safe(driver):
        while True:
            try:
                el = driver.select("title", None)
                if el is not None:
                    return el.text
                else:
                    return driver.run_js("return document.title")
                
            except DetachedElementException:
                print("Title element is detached, Regetting")
                pass
            
def get_inside_input_selector(type):
    if type == "text":
        return "input,textarea"
    elif type == "checkbox":
        return "input"
    else:
        return "input,textarea,select"


def get_input_el(driver, label, wait, type):
    els = driver.get_all_elements_containing_text(label, wait=wait)
    # Prioritize Label Elements
    for el in els:
        if el.tag_name == "label":
            for_attr = el.attributes.get("for")
            if for_attr:
                input_elem = driver.select(
                    get_for_input_selector(type, for_attr),
                    None,
                )
            else:
                input_elem = el.select(get_inside_input_selector(type), wait=None)

            if input_elem:
                return input_elem

    for el in els:
        if el.tag_name != "label":

            label_elem = el.get_parent_which_is("label")
            if label_elem:
                for_attr = label_elem.attributes.get("for")
                if for_attr:
                    input_elem = driver.select(
                        get_for_input_selector(type, for_attr),
                        None,
                    )
                else:
                    input_elem = label_elem.select(
                        get_inside_input_selector(type), wait=None
                    )

                if input_elem:
                    return input_elem

    return None





def base64_decode(encoded_str):
    from base64 import b64decode
    """
    Decodes a base64 encoded string.
    
    :param encoded_str: A base64 encoded string.
    :return: The decoded string.
    """
    # Decoding the base64 encoded string
    decoded_bytes = b64decode(encoded_str)
    # Converting the bytes to string
    decoded_str = decoded_bytes.decode("utf-8")

    return decoded_str

class Response(ContraDict):
    def __init__(self, request_id, content, is_base_64):
        self.request_id = request_id
        self.content = content
        self.is_base_64 = is_base_64
        super().__init__(self.to_dict())

    def to_dict(self):
        return {
            "request_id": self.request_id,
            "content": self.content,
            "is_base_64": self.is_base_64,
        }

    def get_decoded_content(self):
        """
        Decodes the content if it's Base64 encoded, otherwise returns it as-is.
        """
        if self.is_base_64:
            try:
                return base64_decode(self.content)
            except Exception as e:
                raise ValueError(f"Error decoding base64 content: {e}")
        return self.content

    def get_json_content(self):
        """
        Attempts to parse the content as JSON.
        """
        try:
            return json.loads(self.get_decoded_content())
        except json.JSONDecodeError as e:
            raise ValueError(f"Error decoding JSON content: {e}")

    def __repr__(self):
        return f"Response(request_id={self.request_id}, content={self.content}, is_base_64={self.is_base_64})"

class Responses(list):
        def __init__(self, driver:'Driver'):
            super().__init__()
            self.driver = driver

        def collect(self):
            return self.driver.collect_responses(self)

        def clear(self):
            super().clear()


def generate_random_string(length: int = 32) -> str:
    import random
    import string
    letters = string.ascii_letters
    return ''.join(random.choice(letters) for i in range(length))

class Driver(BrowserTab):
    def __init__(
        self,
        headless=False,
        enable_xvfb_virtual_display=False,
        proxy=None,
        profile=None,
        tiny_profile=False,
        block_images=False,
        block_images_and_css=False,
        wait_for_complete_page_load=True,
        chrome_executable_path=None,
        extensions=[],
        arguments=[],
        remove_default_browser_check_argument = False,
        user_agent=None,
        window_size=None,
        lang=None,
        beep=False,
        host=None,
        port=None,
    ):
        self.config = Config(
            headless=headless,
            enable_xvfb_virtual_display=enable_xvfb_virtual_display,
            proxy=proxy,
            profile=profile,
            tiny_profile=tiny_profile,
            block_images=block_images,
            block_images_and_css=block_images_and_css,
            wait_for_complete_page_load=wait_for_complete_page_load,
            chrome_executable_path=chrome_executable_path,
            extensions=extensions,
            arguments=arguments,
            remove_default_browser_check_argument=remove_default_browser_check_argument,
            user_agent=user_agent,
            window_size=window_size,
            lang=lang,
            beep=beep,
            host=host,
            port=port,
        )

        self._tab_value: Tab = None
        self._browser: Browser = start(self.config)
        self._dot_name = None
        self._cursor = None
        self._is_human_mode_enabled = False

        if self.config.tiny_profile:
            load_cookies(self, self.config.profile)

        super().__init__(self.config, self._tab_value,  None, self, self._browser)


    def _make_element(self, elem):
        return make_element(self._driver, self._tab, self, elem)

    def _get_bounding_rect_with_iframe_offset(self):
        return DictPosition(None)

    @property
    def is_human_mode_enabled(self):
        return self._is_human_mode_enabled

    def enable_human_mode(self):
        from botasaurus_humancursor import WebCursor
        self._is_human_mode_enabled = True
        if not self._dot_name:
            self._dot_name = generate_random_string()
        
        if not self._cursor:
            self._cursor = WebCursor(self, self._dot_name)

    def disable_human_mode(self):
        self._is_human_mode_enabled = False




    @property
    def user_agent(self):
        return self.run_js("return navigator.userAgent")



    @property
    def profile(self):
        from .profile import Profile

        if not self.config.profile:
            raise NoProfileException()
        return Profile(self.config.profile)

    @profile.setter
    def profile(self, value):
        from .profile import Profiles

        if not self.config.profile:
            raise NoProfileException()

        if value is None:
            Profiles.delete_profile(self.config.profile)
        elif isinstance(value, dict):
            Profiles.set_profile(self.config.profile, value)
        else:
            raise InvalidProfileException()
        
    def get(self, link: str, bypass_cloudflare=False, js_to_run_before_new_document: str = None, wait: Optional[int] = None,  timeout=60) -> Tab:
            self.run_on_new_document(js_to_run_before_new_document)
            self._tab = self._browser.get(link, )
            self.sleep(wait)
            wait_till_document_is_ready(self._tab, self.config.wait_for_complete_page_load, timeout=timeout)
            if bypass_cloudflare:
                self.detect_and_bypass_cloudflare()
            return self._tab

    def open_link_in_new_tab(self, link: str, bypass_cloudflare=False, js_to_run_before_new_document: str = None, wait: Optional[int] = None,  timeout=60) -> Tab:
            self.run_on_new_document(js_to_run_before_new_document)
            self._tab = self._browser.get(link, new_tab=True, )
            self.sleep(wait)
            wait_till_document_is_ready(self._tab, self.config.wait_for_complete_page_load, timeout=timeout)
            if bypass_cloudflare:
                self.detect_and_bypass_cloudflare()
            return self._tab

    def get_via(
            self,
            link: str,
            referer: str,
            bypass_cloudflare=False,
            js_to_run_before_new_document: str = None,
            wait: Optional[int] = None,
            timeout=60,
        ) -> Tab:
            self.run_on_new_document(js_to_run_before_new_document)
            referer = referer.rstrip("/") + "/"
            self._tab = self._browser.get(link, referrer=referer, )
            self.sleep(wait)
            wait_till_document_is_ready(self._tab, self.config.wait_for_complete_page_load, timeout=timeout)

            if bypass_cloudflare:
                self.detect_and_bypass_cloudflare()
            return self._tab

    def google_get(
            self,
            link: str,
            bypass_cloudflare=False,
            js_to_run_before_new_document: str = None,
            wait: Optional[int] = None,
            accept_google_cookies: bool = False,
            timeout=60,
        ) -> Tab:
            if accept_google_cookies:
                # No need to accept cookies multiple times
                if (
                    hasattr(self, "has_accepted_google_cookies")
                    and self.has_accepted_google_cookies
                ):
                    pass
                else:
                    self.get("https://www.google.com/", js_to_run_before_new_document=js_to_run_before_new_document)
                    if '/sorry/' in self.current_url:
                        print('Blocked by Google')
                    else:
                        perform_accept_google_cookies_action(self)
                        self.has_accepted_google_cookies = True
            self.get_via(
                link,
                "https://www.google.com/",
                bypass_cloudflare=bypass_cloudflare,
                wait=wait,
                js_to_run_before_new_document=js_to_run_before_new_document,
                timeout=timeout,
            )
            return self._tab

    def get_via_this_page(
            self, link: str, bypass_cloudflare=False, js_to_run_before_new_document: str = None, wait: Optional[int] = None,  timeout=60
        ) -> Tab:
            
            self.run_on_new_document(js_to_run_before_new_document)
            currenturl = self.current_url
            self.run_js(f'window.location.href = "{link}";')
            if currenturl != link:
                while True:
                    if currenturl != self.current_url:
                        break
                    time.sleep(0.1)
            self.sleep(wait)

            wait_till_document_is_ready(self._tab, self.config.wait_for_complete_page_load, timeout=timeout)

            if bypass_cloudflare:
                self.detect_and_bypass_cloudflare()

            return self._tab
    def reload(self, js_to_run_before_new_document=None) -> Tab:
        self._tab.reload(script_to_evaluate_on_load=make_iife(load_script_if_js_file(js_to_run_before_new_document)))
        wait_till_document_is_ready(self._tab, self.config.wait_for_complete_page_load)
        return self._tab


    def is_in_page(self, target: str) -> bool:
        return self.wait_for_page_to_be(target, wait=None, raise_exception=False)

    def wait_for_page_to_be(
        self,
        expected_url: Union[str, List[str]],
        wait: Optional[int] = 8,
        raise_exception: bool = True
    ) -> bool:
        def check_page(driver, expected_url):
            if expected_url.startswith("https://") or expected_url.startswith(
                "http://"
            ):
                if isinstance(expected_url, str):
                    return expected_url == driver.current_url
                else:
                    for url in expected_url:
                        if url == driver.current_url:
                            return True
                return False
            else:
                if isinstance(expected_url, str):
                    return expected_url in driver.current_url
                else:
                    for x in expected_url:
                        if x in driver.current_url:
                            return True
                    return False

        if wait is None:
            if check_page(self, expected_url):
                wait_till_document_is_ready(self._tab, True)
                return True
        else:
            time = 0
            while time < wait:
                if check_page(self, expected_url):
                    wait_till_document_is_ready(self._tab, True)
                    return True
                sleep_time = 0.2
                time += sleep_time
                sleep(sleep_time)

            if raise_exception:
                raise PageNotFoundException(expected_url, wait)
            return False

    def switch_to_tab(
        self, tab: Tab
    ) -> Tab:
        self._tab = tab

    def open_in_devtools(self) -> None:
        self._tab.open_external_inspector()


    def sleep(self, n: int) -> None:
        sleep_for_n_seconds(n)

    def short_random_sleep(self) -> None:
        sleep_for_n_seconds(round(uniform(2, 4), 2))

    def long_random_sleep(self) -> None:
        sleep_for_n_seconds(round(uniform(6, 9), 2))

    def sleep_forever(self) -> None:
        sleep_forever()

    def block_urls(self, urls) -> None:
        self._tab.block_urls(urls)
    def block_images_and_css(self) -> None:
        self._tab.block_images_and_css()

    def block_images(self) -> None:
        self._tab.block_images()

    def grant_all_permissions(self):
        self._browser.grant_all_permissions()

    def allow_insecure_connections(self) -> None:
        self._tab.bypass_insecure_connection_warning()


    def close(self) -> None:
        if self.config.tiny_profile:
            save_cookies(self, self.config.profile)
        # You usually don't need to close it because we automatically close it when script is cancelled (ctrl + c) or completed
        self._browser.close()
