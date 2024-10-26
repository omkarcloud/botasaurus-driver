from random import uniform
from datetime import datetime
from time import sleep
import time
from typing import Optional, Union, List, Any

from .core.config import Config
from .core.custom_storage_cdp import block_urls, enable_network
from .tiny_profile import load_cookies, save_cookies
from . import cdp

from .beep_utils import beep_input
from .driver_utils import (
    convert_to_absolute_path,
    create_video_filename,
    ensure_supports_file_upload,
    ensure_supports_multiple_upload,
    perform_accept_google_cookies_action,
    sleep_for_n_seconds,
    sleep_forever,
)
from .exceptions import (
    CheckboxElementForLabelNotFoundException,
    DetachedElementException,
    ElementWithTextNotFoundException,
    IframeNotFoundException,
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
from .core.tab import Tab
from .core.element import Element as CoreElement


class Wait:
    SHORT = 4
    LONG = 8
    VERY_LONG = 16
def generate_random_string(length: int = 32) -> str:
            import random
            import string
            letters = string.ascii_letters
            return ''.join(random.choice(letters) for i in range(length))


def _get_iframe_tab(driver, internal_elem):
    iframe_tab = None
    all_targets = driver._browser.targets
    internal_frame_id = str(internal_elem.frame_id)
    # print(all_targets, internal_frame_id)
    for tgt in all_targets:
        if str(tgt.target.target_id) == internal_frame_id:
            iframe_tab = tgt
            break
    return iframe_tab


def get_iframe_tab(driver, internal_elem):
    iframe_tab = _get_iframe_tab(driver, internal_elem)

    if iframe_tab:
        return iframe_tab

    start_time = time.time()
    timeout = 8

    while True:
        iframe_tab = _get_iframe_tab(driver, internal_elem)
        if iframe_tab:
            return iframe_tab

        driver._update_targets()

        if time.time() - start_time > timeout:
            internal_frame_id = str(internal_elem.frame_id)
            raise IframeNotFoundException(internal_frame_id)

        time.sleep(0.1)
        # time.sleep(2)


def wait_for_iframe_tab_load(driver, iframe_tab):
    iframe_tab.websocket_url = iframe_tab.websocket_url.replace("iframe", "page")
    # wait_till_document_is_ready(iframe_tab, True)


def create_iframe_element(driver, internal_elem):
    iframe_tab = get_iframe_tab(driver, internal_elem)
    wait_for_iframe_tab_load(driver, iframe_tab)

    return IframeElement(driver.config, iframe_tab, driver._browser)


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
        if str(tgt.target.type_) == "iframe":
            if link:
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


def get_iframe_elem_by_link(driver, link, timeout):
    iframe_tab = get_iframe_tab_by_link(driver, link, timeout)
    if iframe_tab:
        wait_for_iframe_tab_load(driver, iframe_tab)
        return IframeElement(driver.config, iframe_tab, driver._browser)
    return None


def make_element(driver, current_tab, internal_elem):
    if not internal_elem:
        return None
    if internal_elem._node.node_name == "IFRAME":
        return create_iframe_element(driver, internal_elem)
    else:
        return Element(driver, current_tab, internal_elem)


def get_all_parents(node):
    if node is None:
        return []

    parents = []
    current_node = node.parent

    while current_node is not None:
        parents.append(current_node)
        current_node = current_node.parent

    return parents


class Element:
    def __init__(self, driver, tab: Tab, elem: CoreElement):
        self._driver = driver
        self._tab = tab
        self._elem: CoreElement = elem
        self.attributes = self._elem.attrs

    @property
    def text(self):
        return self.run_js("(el) => el.innerText || el.textContent")

    @property
    def html(self):
        return self._tab._run(self._elem.get_html())

    @property
    def tag_name(self):
        return self._elem.tag.lower()

    @property
    def parent(self):
        return (
            make_element(self._driver, self._tab, self._elem.parent)
            if self._elem.parent
            else None
        )

    @property
    def children(self) -> List["Element"]:
        return [make_element(self._driver, self._tab, e) for e in self._elem.children]

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

    def get_bounding_rect(self, absolute=False):
        return self._elem.get_position(absolute)

    def get_shadow_root(self, wait: Optional[int] = Wait.SHORT):
        rect = self.get_bounding_rect()
        x = rect.x
        y = rect.y
        elem_coro = self._tab.get_element_at_point(x, y, wait)
        elem = self._tab._run(elem_coro)
        return make_element(self._driver, self._tab, elem) if elem else None

    def select(self, selector: str, wait: Optional[int] = Wait.SHORT) -> "Element":
        elem_coro = self._elem.query_selector(selector, wait)
        elem = self._tab._run(elem_coro)
        return make_element(self._driver, self._tab, elem)

    def select_all(
        self, selector: str, wait: Optional[int] = Wait.SHORT
    ) -> List["Element"]:
        elems_coro = self._elem.query_selector_all(selector, wait)
        elems = self._tab._run(elems_coro)
        return [make_element(self._driver, self._tab, e) for e in elems]

    def select_iframe(
        self, selector: str, wait: Optional[int] = Wait.SHORT
    ) -> "IframeElement":
        return self.select(selector, wait)

    def click(
        self, selector: Optional[str] = None, wait: Optional[int] = Wait.SHORT
    ) -> None:
        if selector:
            self.wait_for_element(selector, wait).click()
        else:
            self._tab._run(self._elem.click())

    def humane_click(
        self, selector: Optional[str] = None, wait: Optional[int] = Wait.SHORT
    ) -> None:
        if selector:
            self.wait_for_element(selector, wait).humane_click()
        else:
            self._tab._run(self._elem.humane_click())

    # def press_and_hold(
    #     self, selector: Optional[str] = None, wait: Optional[int] = Wait.SHORT
    # ) -> None:
    #     if selector:
    #         self.wait_for_element(selector, wait).press_and_hold()
    #     else:
    #         self._tab._run(self._elem.press_and_hold())            

    def type(
        self,
        text: str,
        selector: Optional[str] = None,
        wait: Optional[int] = Wait.SHORT,
    ) -> None:
        if selector:
            self.wait_for_element(selector, wait).type(text)
        else:
            self._tab._run(self._elem.send_keys(text))

    # def clear(self, selector: Optional[str] = None, wait: Optional[int] = Wait.SHORT) -> None:
    #     if selector:
    #         self.wait_for_element(selector, wait).clear()
    #     else:
    #         self._tab._run(self._elem.clear_input())

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
        elems_coro = self._elem.query_selector_all(
            selector, timeout=wait, node_name="a"
        )
        elems = self._tab._run(elems_coro)

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
        elems_coro = self._elem.query_selector_all(
            selector, timeout=wait, node_name="a"
        )
        elems = self._tab._run(elems_coro)

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
        elems_coro = self._elem.query_selector_all(
            selector, timeout=wait, node_name="img"
        )
        elems = self._tab._run(elems_coro)

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
        elems_coro = self._elem.query_selector_all(
            selector, timeout=wait, node_name="img"
        )
        elems = self._tab._run(elems_coro)

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
        return make_element(
            self._driver,
            self._tab,
            self._tab._run(self._elem.wait_for(selector, timeout=wait)),
        )

    def check_element(
        self, selector: Optional[str] = None, wait: Optional[int] = Wait.SHORT
    ) -> None:
        if selector:
            self.wait_for_element(selector, wait).check_element()
        else:
            self._tab._run(self._elem.check_element())

    def uncheck_element(
        self, selector: Optional[str] = None, wait: Optional[int] = Wait.SHORT
    ) -> None:
        if selector:
            self.wait_for_element(selector, wait).uncheck_element()
        else:
            self._tab._run(self._elem.uncheck_element())

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
        self._tab._run(self._elem.scroll_into_view())

    def upload_file(self, file_path: str) -> None:
        file_path = convert_to_absolute_path(file_path)
        ensure_supports_file_upload(self)
        self._tab._run(self._elem.send_file(file_path))

    def upload_multiple_files(self, file_paths: List[str]) -> None:
        file_paths = [convert_to_absolute_path(file_path) for file_path in file_paths]
        ensure_supports_multiple_upload(self)
        self._tab._run(self._elem.send_file(*file_paths))

    def download_video(
        self,
        filename: Optional[str] = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".mp4",
        wait_for_download_completion: bool = True,
        duration: Optional[Union[int, float]] = None,
    ) -> None:
        relative_path = self._tab._run(
            self._elem.download_video(create_video_filename(filename), duration)
        )

        if wait_for_download_completion:
            while not self.is_video_downloaded():
                sleep(1)

            print(f"View downloaded video at {relative_path}")

    def is_video_downloaded(self) -> bool:
        return self._tab._run(self._elem.is_video_downloaded())

    def save_screenshot(
        self,
        filename: Optional[str] = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".png",
    ) -> None:
        self._tab._run(self._elem.save_screenshot(filename))

    def __repr__(self):
        return self._elem.__repr__()

    def run_js(self, script: str, args: Optional[any]=None) -> Any:
        self._tab._run(self._elem.raise_if_disconnected())

        try:
          return self._tab._run(self._elem.apply(script,args=args,))
        except Exception as e:
          print('An exception occurred')
        


def get_inside_input_selector(type):
    if type == "text":
        return "input,textarea"
    elif type == "checkbox":
        return "input"
    else:
        return "input,textarea,select"


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


def block_if_should(driver):
    if driver.config.block_images_and_css:
        driver.block_images_and_css()
    elif driver.config.block_images:
        driver.block_images()


_user_agent = None


class DriverBase:
    def __init__(self, config, _tab_value, _browser):
        self.config = config
        self._tab_value = _tab_value
        self._browser = _browser
        self.native_fetch_name = None

    def _run(self, coro):
        return coro

    @property
    def _tab(self) -> Tab:
        if not self._tab_value:
            self.get("about:blank")

        return self._tab_value

    @_tab.setter
    def _tab(self, value: Tab):
        self._tab_value = value

    @property
    def current_url(self):
        return self.run_js("return window.location.href")

    @property
    def user_agent(self):
        global _user_agent
        if not _user_agent:
            _user_agent = self.run_js("return navigator.userAgent")
        return _user_agent

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
        return self._run(self._tab.get_content())

    @property
    def local_storage(self):
        return LocalStorage(self)

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

    def _update_targets(self):
        return self._run(self._browser.update_targets())

    def get(self, link: str, bypass_cloudflare=False, wait: Optional[int] = None) -> Tab:
        self._tab = self._run(self._browser.get(link))
        self.sleep(wait)
        wait_till_document_is_ready(self._tab, self.config.wait_for_complete_page_load)
        if bypass_cloudflare:
            self.detect_and_bypass_cloudflare()
        block_if_should(self)
        return self._tab

    def open_link_in_new_tab(self, link: str, bypass_cloudflare=False, wait: Optional[int] = None) -> Tab:
        self._tab = self._run(self._browser.get(link, new_tab=True))
        self.sleep(wait)
        wait_till_document_is_ready(self._tab, self.config.wait_for_complete_page_load)
        if bypass_cloudflare:
            self.detect_and_bypass_cloudflare()
        block_if_should(self)
        return self._tab
        
    def reload(self):
        self.get(self.current_url)

    def get_via(
        self,
        link: str,
        referer: str,
        bypass_cloudflare=False,
        wait: Optional[int] = None,
    ) -> Tab:

        referer = referer.rstrip("/") + "/"
        self._tab = self._run(self._browser.get(link, referrer=referer))

        self.sleep(wait)

        wait_till_document_is_ready(self._tab, self.config.wait_for_complete_page_load)

        if bypass_cloudflare:
            self.detect_and_bypass_cloudflare()
        block_if_should(self)
        return self._tab

    def google_get(
        self,
        link: str,
        bypass_cloudflare=False,
        wait: Optional[int] = None,
        accept_google_cookies: bool = False,
    ) -> Tab:
        if accept_google_cookies:
            # No need to accept cookies multiple times
            if (
                hasattr(self, "has_accepted_google_cookies")
                and self.has_accepted_google_cookies
            ):
                pass
            else:
                self.get("https://www.google.com/")
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
        )
        return self._tab

    def get_via_this_page(
        self, link: str, bypass_cloudflare=False, wait: Optional[int] = None
    ) -> Tab:
        currenturl = self.current_url
        self.run_js(f'window.location.href = "{link}";')
        if currenturl != link:
            while True:
                if currenturl != self.current_url:
                    break
                sleep(0.1)
        self.sleep(wait)

        wait_till_document_is_ready(self._tab, self.config.wait_for_complete_page_load)

        if bypass_cloudflare:
            self.detect_and_bypass_cloudflare()

        block_if_should(self)
        return self._tab

    def switch_to_tab(
        self, tab: Tab
    ) -> Tab:
        self._tab = tab

    def run_js(self, script: str, args: Optional[any]=None) -> Any:
        # Run it in IIFE for isloation
        return self._run(self._tab.evaluate(script,args=args,await_promise=True))

    def run_on_new_document(
        self, script
    ) -> None:
        self.run_cdp_command(cdp.page.enable())
        return self.run_cdp_command(cdp.page.add_script_to_evaluate_on_new_document(script))
        # self.run_cdp_command(cdp.page.add_script_to_evaluate_on_load(script))
        
    def run_cdp_command(self, command) -> Any:
        return self._run(self._tab.run_cdp_command(command))
    
    def prevent_fetch_spying(self) -> Any:
        rand = generate_random_string()
        self.run_on_new_document(f"window.{rand} = window.fetch")
        self.native_fetch_name = rand

    def open_in_devtools(self) -> None:
        self._tab.open_external_inspector()

    def get_js_variable(self, variable_name: str) -> Any:
        return self._run(self._tab.js_dumps(variable_name))

    def select(self, selector: str, wait: Optional[int] = Wait.SHORT) -> Element:
        elem = self._run(self._tab.select(selector, timeout=wait))
        return make_element(self, self._tab, elem) if elem else None
    
    def click_at_point(self, x: int, y:int):
        self._run(self._tab.click_at_point(
            x, y
        ))

    def select_all(
        self, selector: str, wait: Optional[int] = Wait.SHORT
    ) -> List[Element]:
        elems_coro = self._tab.select_all(selector, timeout=wait)
        elems = self._run(elems_coro)
        return [make_element(self, self._tab, e) for e in elems]
    
    def count(
        self, selector: str, wait: Optional[int] = Wait.SHORT
    ) -> List[Element]:
        elems_coro = self._tab.count_select(selector, timeout=wait)
        return self._run(elems_coro)


    def select_iframe(
        self, selector: str, wait: Optional[int] = Wait.SHORT
    ) -> "IframeElement":
        return self.select(selector, wait)

    def get_element_containing_text(
        self,
        text: str,
        wait: Optional[int] = Wait.SHORT,
        type: Optional[str] = None,
    ) -> Element:
        elem_coro = self._tab.find(text, type=type, timeout=wait)
        elem = self._run(elem_coro)
        return make_element(self, self._tab, elem) if elem else None

    def get_all_elements_containing_text(
        self,
        text: str,
        wait: Optional[int] = Wait.SHORT,
        type: Optional[str] = None,
    ) -> List[Element]:
        elems_coro = self._tab.find_all(text, type=type, timeout=wait)
        elems = self._run(elems_coro)
        return [make_element(self, self._tab, e) for e in elems]

    def get_element_with_exact_text(
        self,
        text: str,
        wait: Optional[int] = Wait.SHORT,
        type: Optional[str] = None,
    ) -> Element:
        elem_coro = self._tab.find(text, type=type, timeout=wait, exact_match=True)
        elem = self._run(elem_coro)
        return make_element(self, self._tab, elem) if elem else None

    def get_all_elements_with_exact_text(
        self,
        text: str,
        wait: Optional[int] = Wait.SHORT,
        type: Optional[str] = None,
    ) -> List[Element]:
        elems_coro = self._tab.find_all(text, type=type, timeout=wait, exact_match=True)
        elems = self._run(elems_coro)
        return [make_element(self, self._tab, e) for e in elems]

    def get_element_at_point(
        self,
        x: int,
        y: int,
        child_selector: Optional[str] = None,
        wait: Optional[int] = Wait.SHORT,
    ) -> Element:
        elem_coro = self._tab.get_element_at_point(x, y, wait)
        elem = self._run(elem_coro)
        el = make_element(self, self._tab, elem) if elem else None

        if not el:
            return

        if child_selector:
            selected_el = el.select(child_selector, wait=None)
            if selected_el:
                return selected_el
            else:
                if wait:
                    now = time.time()
                    while not selected_el:
                        elem_coro = self._tab.get_element_at_point(x, y, None)
                        elem = self._run(elem_coro)
                        el = make_element(self, self._tab, elem) if elem else None
                        if el:
                            selected_el = el.select(child_selector, wait=None)
                        if time.time() - now > wait:
                            return selected_el
                        time.sleep(0.2)
                return selected_el

        return el

    def get_iframe_by_link(
        self, link_regex: Optional[str] = None, wait: Optional[int] = Wait.SHORT
    ):
        return get_iframe_elem_by_link(self, link_regex, wait)

    def is_element_present(self, selector: str, wait: Optional[int] = None) -> bool:
        return self.select(selector, wait) is not None

    def click(self, selector: str, wait: Optional[int] = Wait.SHORT) -> None:
        elem = self.wait_for_element(selector, wait)
        elem.click()

    def humane_click(self, selector: str, wait: Optional[int] = Wait.SHORT) -> None:
        elem = self.wait_for_element(selector, wait)
        elem.humane_click()

    # def press_and_hold(self, selector: str, wait: Optional[int] = Wait.SHORT) -> None:
    #     elem = self.wait_for_element(selector, wait)
    #     elem.press_and_hold()

    def click_element_containing_text(
        self, text: str, wait: Optional[int] = Wait.SHORT
    ) -> None:
        elem = self.get_element_containing_text(text, wait)

        if elem is None:
            raise ElementWithTextNotFoundException(text)

        elem.click()

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
        input_elem = get_input_el(self, label, wait, "checkbox")
        if input_elem:
            input_elem.uncheck_element()
        else:
            raise CheckboxElementForLabelNotFoundException(label)

    def get_link(
        self,
        selector: str,
        url_contains_text: Optional[str] = None,
        element_contains_text: Optional[str] = None,
        wait: Optional[int] = Wait.SHORT,
    ) -> str:
        elems_coro = self._tab.select_all(selector, timeout=wait, node_name="a")
        elems = self._run(elems_coro)

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
        elems_coro = self._tab.select_all(
            selector if selector else "a[href]", timeout=wait, node_name="a"
        )
        elems = self._run(elems_coro)

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
        elems_coro = self._tab.select_all(selector, timeout=wait, node_name="img")
        elems = self._run(elems_coro)

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
        elems_coro = self._tab.select_all(
            selector if selector else "img[src]", timeout=wait, node_name="img"
        )
        elems = self._run(elems_coro)

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
        return make_element(
            self, self._tab, self._run(self._tab.wait_for(selector, timeout=wait))
        )

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

    def sleep(self, n: int) -> None:
        sleep_for_n_seconds(n)

    def short_random_sleep(self) -> None:
        sleep_for_n_seconds(uniform(2, 4))

    def long_random_sleep(self) -> None:
        sleep_for_n_seconds(uniform(6, 9))

    def sleep_forever(self) -> None:
        sleep_forever()

    def get_bot_detected_by(self) -> str:
        # or script[data-cf-beacon]
        # clf = self.select("#challenge-running, script[data-cf-beacon]", wait=None)
        if (
            self.get_iframe_by_link("challenges.cloudflare.com", None) is not None
            or self.title == "Just a moment..."
        ):
            return Opponent.CLOUDFLARE
        if self.select("script[data-cf-beacon]", None):
            # Wait for the iframe to render
            if self.get_iframe_by_link("challenges.cloudflare.com", 12):
                return Opponent.CLOUDFLARE
        pmx = self.get_element_containing_text(
            "Please verify you are a human", wait=None
        )

        if pmx is not None:
            return Opponent.PERIMETER_X

        return None

    def is_bot_detected(self) -> bool:
        return self.get_bot_detected_by() is not None

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
        return self._run(self._browser.cookies.get_all())

    def get_local_storage(self) -> dict:
        storage = self.local_storage
        return storage.items()

    def get_cookies_and_local_storage(self) -> tuple:
        cookies = self.get_cookies()
        local_storage = self.get_local_storage()

        return {"cookies": cookies, "local_storage": local_storage}

    def add_cookies(self, cookies: List[dict]) -> None:
        return self._run(self._browser.cookies.set_all(cookies))

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
        return self._run(self._browser.cookies.clear())

    def delete_local_storage(self) -> None:
        self.run_js("window.localStorage.clear();")
        self.run_js("window.sessionStorage.clear();")

    def delete_cookies_and_local_storage(self) -> None:
        self.delete_cookies()
        self.delete_local_storage()

    def is_in_page(self, target: str) -> bool:
        return self.wait_for_page_to_be(target, wait=None, raise_exception=False)

    def wait_for_page_to_be(
        self,
        expected_url: Union[str, List[str]],
        wait: Optional[int] = 8,
        raise_exception: bool = True,
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

    def save_screenshot(
        self,
        filename: Optional[str] = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".png",
    ) -> None:
        self._run(self._tab.save_screenshot(filename=filename))

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
        self._run(self._tab.download_file(url, filename))

    def __repr__(self):
        return self._tab.__repr__()


class IframeElement(DriverBase):

    @property
    def iframe_url(self) -> Tab:
        return self._tab_value.target.url


class Driver(DriverBase):
    def __init__(
        self,
        headless=False,
        proxy=None,
        profile=None,
        tiny_profile=False,
        block_images=False,
        block_images_and_css=False,
        wait_for_complete_page_load=True,
        extensions=[],
        arguments=[],
        user_agent=None,
        window_size=None,
        lang=None,
        beep=False,
    ):

        self.config = Config(
            headless=headless,
            proxy=proxy,
            profile=profile,
            tiny_profile=tiny_profile,
            block_images=block_images,
            block_images_and_css=block_images_and_css,
            wait_for_complete_page_load=wait_for_complete_page_load,
            extensions=extensions,
            arguments=arguments,
            user_agent=user_agent,
            window_size=window_size,
            lang=lang,
            beep=beep,
        )
        self._tab_value: Tab = None

        self._browser: Browser = self._run(start(self.config))

        block_if_should(self)

        if self.config.tiny_profile:
            load_cookies(self, self.config.profile)

        super().__init__(self.config, self._tab_value, self._browser)

    def block_urls(self, urls) -> None:
        # You usually don't need to close it because we automatically close it when script is cancelled (ctrl + c) or completed
        self.run_cdp_command(enable_network())
        self.run_cdp_command(block_urls(urls))

    def block_images_and_css(self) -> None:
        self.block_urls(
            [
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
        )

    def block_images(self) -> None:
        self.block_urls(
            [
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
        )

    def close(self) -> None:
        if self.config.tiny_profile:
            save_cookies(self, self.config.profile)
        # You usually don't need to close it because we automatically close it when script is cancelled (ctrl + c) or completed
        self._browser.close()
